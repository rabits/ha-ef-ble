"""Config flow for EcoFlow BLE integration."""

from __future__ import annotations

import base64
import logging
from collections.abc import Mapping
from functools import cached_property
from typing import Any, ClassVar

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    CONN_CLASS_LOCAL_PUSH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from . import eflib
from .const import (
    CONF_LOG_BLEAK,
    CONF_LOG_CONNECTION,
    CONF_LOG_ENCRYPTED_PAYLOADS,
    CONF_LOG_MASKED,
    CONF_LOG_MESSAGES,
    CONF_LOG_PACKETS,
    CONF_LOG_PAYLOADS,
    CONF_UPDATE_PERIOD,
    CONF_USER_ID,
    DOMAIN,
)
from .eflib.connection import ConnectionState
from .eflib.logging_util import LogOptions

_LOGGER = logging.getLogger(__name__)


class EFBLEConfigFlow(ConfigFlow, domain=DOMAIN):
    """EcoFlow BLE ConfigFlow"""

    VERSION = 1
    MINOR_VERSION = 0

    CONNECTION_CLASS = CONN_CLASS_LOCAL_PUSH

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_device: eflib.DeviceBase | None = None
        self._discovered_devices: dict[str, eflib.DeviceBase] = {}

        self._user_id: str = ""
        self._email: str = ""
        self._user_id_validated: bool = False
        self._log_options = LogOptions(0)
        self._collapsed = True

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(unique_id=discovery_info.address)
        self._abort_if_unique_id_configured()

        device = eflib.NewDevice(discovery_info.device, discovery_info.advertisement)
        if device is None:
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        self._discovered_device = device
        _LOGGER.debug("Discovered device: %s", device)
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovered_device is not None
        device = self._discovered_device
        assert self._discovery_info is not None

        errors = {}
        title = device.name_by_user or device.name
        _LOGGER.debug("Confirm discovery: %s, %s", title, user_input)

        if data := await self._store.async_load():
            self._user_id = data["user_id"]

        self._set_confirm_only()

        placeholders = {"name": title}
        self.context["title_placeholders"] = placeholders

        if user_input is not None:
            errors |= await self._validate_user_id(self._discovered_device, user_input)
            if not errors and self._user_id_validated:
                user_input[CONF_ADDRESS] = device.address
                user_input.pop("login")
                return self.async_create_entry(title=title, data=user_input)
            self._log_options = ConfLogOptions.from_config(user_input)

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=placeholders,
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USER_ID, default=self._user_id): str,
                    **self._login_option(),
                    vol.Required(CONF_ADDRESS): vol.In([f"{title} ({device.address})"]),
                    **_update_period_option(),
                    **ConfLogOptions.schema(
                        ConfLogOptions.to_config(self._log_options)
                    ),
                }
            ),
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        errors = {}

        if data := await self._store.async_load():
            self._user_id = data["user_id"]

        if user_input is not None:
            try:
                device = self._discovered_devices[user_input[CONF_ADDRESS]]
                address = device.address
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                title = device.name_by_user or device.name
                errors |= await self._validate_user_id(device, user_input)
                if not errors and self._user_id_validated:
                    user_input[CONF_ADDRESS] = device.address
                    user_input.pop("login")

                    return self.async_create_entry(title=title, data=user_input)
                self._log_options = ConfLogOptions.from_config(user_input)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            device = eflib.NewDevice(
                discovery_info.device, discovery_info.advertisement
            )
            if device is not None:
                name = device.name_by_user or device.name
                self._discovered_devices[f"{name} ({address})"] = device

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USER_ID, default=self._user_id): str,
                    **self._login_option(),
                    vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices.keys()),
                    **_update_period_option(),
                    **ConfLogOptions.schema(
                        ConfLogOptions.to_config(self._log_options)
                    ),
                }
            ),
        )

    def _login_option(self):
        return {
            vol.Required("login"): section(
                vol.Schema(
                    {
                        vol.Optional(CONF_EMAIL, default=self._email): str,
                        vol.Optional(CONF_PASSWORD, default=""): str,
                    }
                ),
                {"collapsed": self._collapsed},
            ),
        }

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfiguration of the picked device."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            try:
                address = reconfigure_entry.data.get(CONF_ADDRESS)
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates=user_input,
                )
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USER_ID, default=reconfigure_entry.data.get(CONF_USER_ID)
                    ): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry[eflib.DeviceBase],
    ) -> OptionsFlow:
        return OptionsFlowHandler()

    async def _validate_user_id(
        self, device: eflib.DeviceBase, user_input: dict[str, Any]
    ):
        self._user_id_validated = False

        self._email = user_input.get("login", {}).get(CONF_EMAIL, "")
        password = user_input.get("login", {}).get(CONF_PASSWORD, "")
        user_id = user_input.get(CONF_USER_ID, "")

        self._collapsed = False

        if not self._email and not password and not user_id:
            return {CONF_USER_ID: "User ID cannot be empty"}

        if self._email or password:
            if not self._email:
                return {"login": "email_empty"}
            if not password:
                return {"login": "password_empty"}
            return await self._ecoflow_login(self._email, password)

        self._user_id = user_id

        device.with_logging_options(ConfLogOptions.from_config(user_input))

        await device.connect(self._user_id, max_attempts=4)
        await device.waitConnected(timeout=20)
        conn_state = device.connection_state
        await device.disconnect()

        error = None
        match conn_state:
            case ConnectionState.INIT:
                error = "error_try_refresh"
            case ConnectionState.ERROR_AUTH_FAILED:
                error = "device_auth_failed"
            case ConnectionState.ERROR_TIMEOUT:
                error = "bt_timeout"
            case ConnectionState.ERROR_NOT_FOUND:
                error = "bt_not_found"
            case ConnectionState.ERROR_BLEAK:
                error = "bt_general_error"
            case ConnectionState.ERROR_UNKNOWN:
                error = "unknown"
            case ConnectionState.AUTHENTICATED:
                self._user_id_validated = True
                await self._store.async_save(data={"user_id": self._user_id})

        await device.waitDisconnected()

        if error is not None:
            return {"base": error}
        return {}

    @cached_property
    def _store(self):
        return Store(self.hass, self.VERSION, f"{DOMAIN}.user_id")

    async def _ecoflow_login(self, email: str, password: str):
        session = async_get_clientsession(self.hass)
        async with session.post(
            url="https://api.ecoflow.com/auth/login",
            json={
                "scene": "IOT_APP",
                "appVersion": "1.0.0",
                "password": base64.b64encode(password.encode()).decode(),
                "oauth": {
                    "bundleId": "com.ef.EcoFlow",
                },
                "email": email,
                "userType": "ECOFLOW",
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        ) as response:
            response.raise_for_status()

            result_json = await response.json()
            if result_json["code"] != "0":
                return {"login": f"Login failed: '{result_json['message']}'"}

            self._user_id = result_json["data"]["user"]["userId"]
        self._email = ""
        self._collapsed = True
        return {}


class OptionsFlowHandler(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        merged_entry = self.config_entry.data | self.config_entry.options
        options = {
            CONF_UPDATE_PERIOD: merged_entry.get(CONF_UPDATE_PERIOD, 0),
        }

        device: eflib.DeviceBase | None = getattr(
            self.config_entry, "runtime_data", None
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        **_update_period_option(),
                        **ConfLogOptions.schema(merged_entry, False),
                    }
                ),
                options,
            ),
            description_placeholders={
                "device_name": device.device if device else "Ecoflow Device"
            },
        )


class ConfLogOptions:
    _CONF_OPTION_TO_LOG_OPTION: ClassVar = {
        CONF_LOG_MASKED: LogOptions.MASKED,
        CONF_LOG_CONNECTION: LogOptions.CONNECTION_DEBUG,
        CONF_LOG_MESSAGES: LogOptions.DESERIALIZED_MESSAGES,
        CONF_LOG_PACKETS: LogOptions.PACKETS,
        CONF_LOG_PAYLOADS: LogOptions.DECRYPTED_PAYLOADS,
        CONF_LOG_ENCRYPTED_PAYLOADS: LogOptions.ENCRYPTED_PAYLOADS,
        CONF_LOG_BLEAK: LogOptions.BLEAK_DEBUG,
    }

    CONF_KEY = "log_options"

    @classmethod
    def from_config(cls, config_entry: Mapping[str, Any]):
        config_entry = config_entry.get(cls.CONF_KEY, config_entry)
        log_options = LogOptions(0)
        for conf_option, log_option in cls._CONF_OPTION_TO_LOG_OPTION.items():
            if config_entry.get(conf_option, False):
                log_options |= log_option
        return log_options

    @classmethod
    def to_config(cls, options: LogOptions):
        reversed_option_map = {v: k for k, v in cls._CONF_OPTION_TO_LOG_OPTION.items()}
        return {reversed_option_map[option]: True for option in options}

    @classmethod
    def schema(
        cls, defaults_dict: Mapping[str, Any] | None = None, collapsed: bool = True
    ):
        if defaults_dict is None:
            defaults_dict = {}

        defaults_dict = defaults_dict.get(cls.CONF_KEY, defaults_dict)

        return {
            vol.Required(cls.CONF_KEY): section(
                vol.Schema(
                    {
                        **{
                            vol.Optional(
                                option, default=defaults_dict.get(option, False)
                            ): bool
                            for option in cls._CONF_OPTION_TO_LOG_OPTION
                        },
                    }
                ),
                {"collapsed": collapsed},
            ),
        }


def _update_period_option(default: int = 0):
    return {
        vol.Optional(CONF_UPDATE_PERIOD, default=default): vol.All(
            int, vol.Range(min=0)
        )
    }

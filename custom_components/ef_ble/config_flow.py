"""Config flow for EcoFlow BLE integration."""

from __future__ import annotations

import asyncio
import base64
import enum
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
from homeassistant.const import CONF_ADDRESS, CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.storage import Store

from . import eflib
from .const import (
    CONF_COLLECT_PACKETS,
    CONF_COLLECT_PACKETS_AMOUNT,
    CONF_CONNECTION_TIMEOUT,
    CONF_LOG_BLEAK,
    CONF_LOG_CONNECTION,
    CONF_LOG_ENCRYPTED_PAYLOADS,
    CONF_LOG_MASKED,
    CONF_LOG_MESSAGES,
    CONF_LOG_PACKETS,
    CONF_LOG_PAYLOADS,
    CONF_PACKET_VERSION,
    CONF_UPDATE_PERIOD,
    CONF_USER_ID,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_UPDATE_PERIOD,
    DOMAIN,
    LINK_WIKI_SUPPORTING_NEW_DEVICES,
)
from .eflib.connection import ConnectionState
from .eflib.logging_util import LogOptions

_LOGGER = logging.getLogger(__name__)


class PacketVersion(enum.StrEnum):
    """Enum for mapping packet version numbers to strings used from HA"""

    V2 = "v2"
    V3 = "v3"

    def to_num(self):
        """Get packet version as number used for device config"""
        return int(self.value.split("v")[1])

    @classmethod
    def from_str(cls, value: str | None):
        """Get PacketVersion from string, defaulting to V3 if invalid"""
        try:
            return cls(value)
        except ValueError:
            return PacketVersion.V3


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
        self._device_by_display_name: dict[str, eflib.DeviceBase] = {}
        self._local_names: dict[str, str] = {}

        self._user_id: str = ""
        self._email: str = ""
        self._user_id_validated: bool = False
        self._log_options = LogOptions.no_options()
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
        self._set_name_from_discovery(self._discovery_info, device.name)

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
        title = f"{device.device} ({self._local_names[device.address]})"

        if data := await self._store.async_load():
            self._user_id = data["user_id"]

        self._set_confirm_only()

        placeholders = {"name": title}
        self.context["title_placeholders"] = placeholders

        if user_input is not None:
            errors |= await self._validate_user_id(self._discovered_device, user_input)
            if not errors and self._user_id_validated:
                return self._create_entry(user_input, device)
            self._log_options = ConfLogOptions.from_config(user_input)

        full_name = (
            f"{device.device} - {self._local_names[device.address]} [{device.address}]"
        )
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=placeholders,
            errors=errors,
            data_schema=(
                schema_builder()
                .user_id(self._user_id)
                .login(self._email, self._collapsed)
                .required(CONF_ADDRESS, vol.In([full_name]))
                .update_period()
                .timeout()
                .conf_log(self._log_options)
                .build()
            ),
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""

        if user_input is not None:
            self._discovered_device = self._device_by_display_name[
                user_input[CONF_ADDRESS]
            ]

            if eflib.is_unsupported(self._discovered_device):
                return await self.async_step_unsupported_device()

            return await self.async_step_device_confirm()

        current_addresses = self._async_current_ids()

        for discovery_info in async_discovered_service_info(self.hass):
            address = discovery_info.address
            self._set_name_from_discovery(discovery_info)
            if address in current_addresses or address in self._discovered_devices:
                continue

            device = eflib.NewDevice(
                discovery_info.device, discovery_info.advertisement
            )

            if device is not None:
                self._discovered_devices[address] = device
                self._set_name_from_discovery(discovery_info, device.name)
                name = f"{self._local_names[address]} - {device.device}"
                if eflib.is_unsupported(device):
                    name = f"[Unsupported] {name.replace('[Unsupported]', '')}"
                self._device_by_display_name[f"{name} ({address})"] = device

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        device_by_name_sorted = dict(
            sorted(
                self._device_by_display_name.items(),
                key=lambda item: eflib.is_unsupported(item[1]),
            )
        )

        return self.async_show_form(
            step_id="user",
            last_step=False,
            description_placeholders={
                "wiki_link": LINK_WIKI_SUPPORTING_NEW_DEVICES,
            },
            data_schema=(
                schema_builder()
                .required(CONF_ADDRESS, vol.In(device_by_name_sorted.keys()))
                .build()
            ),
        )

    def _set_name_from_discovery(
        self, discovery_info: BluetoothServiceInfoBleak, default: str | None = None
    ):
        if (
            local_name := discovery_info.advertisement.local_name
        ) is None or "ecoflow" in local_name.lower():
            if default is None:
                return

            local_name = default

        self._local_names[discovery_info.address] = local_name

    async def async_step_device_confirm(self, user_input: dict[str, Any] | None = None):
        assert self._discovered_device is not None
        device = self._discovered_device

        errors = {}

        if data := await self._store.async_load():
            self._user_id = data["user_id"]

        if user_input is not None:
            errors |= await self._validate_current_device(user_input)
            if not errors:
                return self._create_entry(user_input, device)

        placeholders = {"name": device.device}
        self.context["title_placeholders"] = placeholders

        return self.async_show_form(
            step_id="device_confirm",
            errors=errors,
            description_placeholders=placeholders,
            data_schema=(
                schema_builder()
                .user_id(self._user_id)
                .login(self._email, self._collapsed)
                .update_period()
                .timeout()
                .conf_log(self._log_options)
                .build()
            ),
        )

    async def async_step_unsupported_device(
        self, user_input: dict[str, Any] | None = None
    ):
        assert eflib.is_unsupported(self._discovered_device)
        device = self._discovered_device

        if data := await self._store.async_load():
            self._user_id = data["user_id"]

        errors = {}
        if user_input is not None:
            errors |= await self._validate_current_device(user_input)
            if not errors:
                return self._create_entry(user_input, device)

        placeholders = {
            "name": device.device,
            "wiki_link": LINK_WIKI_SUPPORTING_NEW_DEVICES,
        }
        self.context["title_placeholders"] = placeholders

        return self.async_show_form(
            step_id="unsupported_device",
            errors=errors,
            description_placeholders=placeholders,
            data_schema=(
                schema_builder()
                .user_id(self._user_id)
                .optional(
                    CONF_PACKET_VERSION,
                    SelectSelector(
                        SelectSelectorConfig(
                            options=list(PacketVersion),
                            mode=SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                    default=PacketVersion.from_str(f"v{device.packet_version}"),
                )
                .login(self._email, self._collapsed)
                .timeout()
                .conf_log(self._log_options)
                .build()
            ),
        )

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
            data_schema=(
                schema_builder()
                .user_id(reconfigure_entry.data.get(CONF_USER_ID))
                .build()
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry[eflib.DeviceBase],
    ) -> OptionsFlow:
        return OptionsFlowHandler()

    async def _validate_current_device(
        self, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        errors = {}
        try:
            assert self._discovered_device is not None

            device = self._discovered_device
            address = device.address

            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            errors |= await self._validate_user_id(device, user_input)
            if not errors and self._user_id_validated:
                return {}

            self._log_options = ConfLogOptions.from_config(user_input)
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        return errors

    def _create_entry(self, user_input: dict[str, Any], device: eflib.DeviceBase):
        entry_data = user_input.copy()
        entry_data[CONF_ADDRESS] = device.address
        entry_data["local_name"] = self._local_names.get(device.address, None)
        entry_data.pop("login", None)

        return self.async_create_entry(title=device.name, data=entry_data)

    async def _validate_user_id(
        self, device: eflib.DeviceBase, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        self._user_id_validated = False

        self._email = user_input.get("login", {}).get(CONF_EMAIL, "")
        password = user_input.get("login", {}).get(CONF_PASSWORD, "")
        region = user_input.get("login", {}).get(CONF_REGION, "")
        user_id = user_input.get(CONF_USER_ID, "")
        timeout = user_input.get(CONF_CONNECTION_TIMEOUT, DEFAULT_CONNECTION_TIMEOUT)
        packet_version = PacketVersion.from_str(user_input.get(CONF_PACKET_VERSION))

        self._collapsed = False

        if not self._email and not password and not user_id:
            return {CONF_USER_ID: "User ID cannot be empty"}

        if self._email or password:
            if not self._email:
                return {"login": "email_empty"}
            if not password:
                return {"login": "password_empty"}
            return await self._ecoflow_login(self._email, password, region)

        self._user_id = user_id

        device.with_logging_options(
            ConfLogOptions.from_config(user_input)
        ).with_packet_version(packet_version.to_num())

        await device.connect(self._user_id)
        try:
            conn_state = await asyncio.wait_for(
                device.wait_until_authenticated_or_error(), timeout
            )
        except TimeoutError:
            conn_state = device.connection_state

        await device.disconnect()

        error = None
        match conn_state:
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
            case _:
                error = (
                    "error_try_refresh"
                    if not eflib.is_unsupported(device)
                    else "error_try_refresh_unsupported"
                )

        await device.wait_disconnected()

        if error is not None:
            return {"base": error}
        return {}

    @cached_property
    def _store(self):
        return Store(self.hass, self.VERSION, f"{DOMAIN}.user_id")

    async def _ecoflow_login(self, email: str, password: str, region: str):
        session = async_get_clientsession(self.hass)

        match region:
            case "EU":
                base_url = "api-e.ecoflow.com"
            case "US":
                base_url = "api-a.ecoflow.com"
            case _:
                base_url = "api.ecoflow.com"

        async with session.post(
            url=f"https://{base_url}/auth/login",
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
            if not response.ok:
                return {
                    "login": (
                        f"Login failed with status code {response.status}: "
                        f"{response.reason}"
                    )
                }

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

        device: eflib.DeviceBase | None = getattr(
            self.config_entry, "runtime_data", None
        )

        merged_entry = self.config_entry.data | self.config_entry.options
        options = {
            CONF_UPDATE_PERIOD: merged_entry.get(
                CONF_UPDATE_PERIOD, DEFAULT_UPDATE_PERIOD
            ),
            CONF_COLLECT_PACKETS: merged_entry.get(
                CONF_COLLECT_PACKETS, eflib.is_unsupported(device)
            ),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                (
                    schema_builder()
                    .update_period(condition=not eflib.is_unsupported(device))
                    .optional(CONF_COLLECT_PACKETS, bool, eflib.is_unsupported(device))
                    .optional(
                        key=CONF_COLLECT_PACKETS_AMOUNT,
                        selector=int,
                        default=(
                            device.diagnostics.packet_buffer_size
                            if device is not None
                            else 100
                        ),
                    )
                    .update(ConfLogOptions.schema(merged_entry, collapsed=False))
                    .build()
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
        log_options = LogOptions.no_options()
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


class _SchemaBuilder:
    def __init__(self, schema: dict | None = None):
        self._schema = schema or {}

    def user_id(self, user_id: str, required: bool = False):
        marker = vol.Required if required else vol.Optional

        return self.update({marker(CONF_USER_ID, default=user_id): str})

    def login(self, email: str, collapsed: bool = True):
        return self.update(
            {
                vol.Required("login"): section(
                    schema=(
                        schema_builder()
                        .optional(CONF_EMAIL, str, email)
                        .optional(CONF_PASSWORD, str, "")
                        .optional(CONF_REGION, vol.In(["Auto", "EU", "US"]), "Auto")
                        .build()
                    ),
                    options={"collapsed": collapsed},
                ),
            }
        )

    def update_period(
        self, default: int = DEFAULT_UPDATE_PERIOD, condition: bool = True
    ):
        return self.optional(
            key=CONF_UPDATE_PERIOD,
            selector=vol.All(int, vol.Range(min=0)),
            default=default,
            condition=condition,
        )

    def timeout(self, default: int = DEFAULT_CONNECTION_TIMEOUT):
        return self.optional(
            key=CONF_CONNECTION_TIMEOUT,
            selector=vol.All(int, vol.Range(min=0)),
            default=default,
        )

    def conf_log(self, options: LogOptions):
        return self.update(ConfLogOptions.schema(ConfLogOptions.to_config(options)))

    def build(self):
        return vol.Schema(self._schema)

    def update(self, entry: dict):
        return _SchemaBuilder(self._schema | entry)

    def required(self, key: str, selector: Any, condition: bool = True):
        if not condition:
            return self

        return self.update({vol.Required(key): selector})

    def optional(
        self,
        key: str,
        selector: Any,
        default: Any = vol.UNDEFINED,
        condition: bool = True,
    ):
        if not condition:
            return self

        return self.update({vol.Optional(key, default=default): selector})


def schema_builder():
    return _SchemaBuilder()

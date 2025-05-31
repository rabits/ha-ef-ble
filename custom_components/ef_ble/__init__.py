"""The unofficial EcoFlow BLE devices integration"""

import logging
from functools import partial

import homeassistant.helpers.issue_registry as ir
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_TYPE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.device_registry import DeviceInfo

from . import eflib
from .config_flow import ConfLogOptions, LogOptions
from .const import (
    CONF_CONNECTION_TIMEOUT,
    CONF_UPDATE_PERIOD,
    CONF_USER_ID,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_UPDATE_PERIOD,
    DOMAIN,
    MANUFACTURER,
)
from .eflib.connection import (
    AuthFailedError,
    BleakError,
    ConnectionTimeout,
    MaxConnectionAttemptsReached,
)
from .eflib.logging_util import ConnectionLog

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
]

type DeviceConfigEntry = ConfigEntry[eflib.DeviceBase]

_LOGGER = logging.getLogger(__name__)

ConfigEntryNotReady = partial(ConfigEntryNotReady, translation_domain=DOMAIN)
ConfigEntryError = partial(ConfigEntryError, translation_domain=DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: DeviceConfigEntry) -> bool:
    """Set up EF BLE device from a config entry."""
    _LOGGER.debug("Init EcoFlow BLE Integration")

    address = entry.data.get(CONF_ADDRESS)
    user_id = entry.data.get(CONF_USER_ID)
    merged_options = entry.data | entry.options
    update_period = merged_options.get(CONF_UPDATE_PERIOD, DEFAULT_UPDATE_PERIOD)
    timeout = merged_options.get(CONF_CONNECTION_TIMEOUT, DEFAULT_CONNECTION_TIMEOUT)

    if address is None or user_id is None:
        return False

    if not bluetooth.async_address_present(hass, address):
        raise ConfigEntryNotReady(translation_key="device_not_present")

    _LOGGER.debug("Connecting Device")
    device: eflib.DeviceBase | None = getattr(entry, "runtime_data", None)
    if device is None:
        discovery_info = bluetooth.async_last_service_info(
            hass, address, connectable=True
        )
        device = eflib.NewDevice(discovery_info.device, discovery_info.advertisement)
        if device is None:
            raise ConfigEntryNotReady(translation_key="unable_to_create_device")

        entry.runtime_data = device

    issue_id = f"{entry.entry_id}_max_connection_attempts"

    try:
        await (
            device.with_update_period(update_period)
            .with_logging_options(ConfLogOptions.from_config(merged_options))
            .with_disabled_reconnect()
            .connect(user_id, timeout=timeout)
        )
        state = await device.wait_until_authenticated_or_error(raise_on_error=True)
    except (ConnectionTimeout, BleakError, TimeoutError) as e:
        raise ConfigEntryNotReady(
            translation_key="could_not_connect",
            translation_placeholders={"time": str(timeout)},
        ) from e
    except AuthFailedError as e:
        raise ConfigEntryNotReady(translation_key="authentication_failed") from e
    except MaxConnectionAttemptsReached as e:
        await device.disconnect()
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="max_connection_attempts_reached",
            translation_placeholders={
                "device_name": device.name,
                "attempts": str(e.attempts),
            },
        )
        raise ConfigEntryError(
            translation_key="could_not_connect_no_retry",
            translation_placeholders={"attempts": str(e.attempts)},
        ) from e
    except Exception as e:
        _LOGGER.exception("Unknown error")
        await device.disconnect()
        raise ConfigEntryNotReady(
            translation_key="unknown_error", translation_placeholders={"error": str(e)}
        ) from e
    else:
        if not state.authenticated():
            await device.disconnect()
            raise ConfigEntryNotReady(
                translation_key="failed_after_successful_connection",
                translation_placeholders={"last_state": state},
            )
    ir.async_delete_issue(hass, DOMAIN, issue_id)

    _LOGGER.debug("Creating entities")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug("Setup done")
    entry.async_on_unload(entry.add_update_listener(_update_listener))

    def _on_disconnect(exc: Exception | type[Exception] | None):
        async def _disconnect_and_reload():
            hass.config_entries.async_schedule_reload(entry.entry_id)

        hass.async_create_task(_disconnect_and_reload())

    entry.async_on_unload(device.on_disconnect(_on_disconnect))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeviceConfigEntry) -> bool:
    """Unload a config entry."""
    device = entry.runtime_data
    await device.disconnect()
    device.with_logging_options(LogOptions.no_options())
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: DeviceConfigEntry):
    ConnectionLog.clean_cache_for(entry.data[CONF_ADDRESS])


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """Device info."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data[CONF_ADDRESS])},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=entry.data.get(CONF_TYPE),
    )


async def _update_listener(hass: HomeAssistant, entry: DeviceConfigEntry):
    device = entry.runtime_data
    merged_options = entry.data | entry.options
    update_period = merged_options.get(CONF_UPDATE_PERIOD, DEFAULT_UPDATE_PERIOD)
    device.with_update_period(period=update_period).with_logging_options(
        ConfLogOptions.from_config(merged_options)
    )

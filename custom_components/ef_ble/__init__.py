"""The unofficial EcoFlow BLE devices integration"""

import logging
from functools import partial

import homeassistant.helpers.issue_registry as ir
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import eflib
from .config_flow import CONF_COLLECT_PACKETS, ConfLogOptions, LogOptions, PacketVersion
from .const import (
    CONF_CONNECTION_TIMEOUT,
    CONF_PACKET_VERSION,
    CONF_UPDATE_PERIOD,
    CONF_USER_ID,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_UPDATE_PERIOD,
    DOMAIN,
)
from .eflib.connection import (
    BleakError,
    ConnectionTimeout,
    MaxConnectionAttemptsReached,
)
from .eflib.exceptions import AuthErrors
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
    raw_pv = entry.data.get(CONF_PACKET_VERSION)
    packet_version = PacketVersion.from_str(raw_pv).to_num() if raw_pv else None

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

    packet_collection_enabled = merged_options.get(
        CONF_COLLECT_PACKETS, eflib.is_unsupported(device)
    )
    issue_id = f"{entry.entry_id}_max_connection_attempts"

    try:
        await (
            device.with_update_period(update_period)
            .with_logging_options(ConfLogOptions.from_config(merged_options))
            .with_disabled_reconnect()
            .with_packet_version(packet_version)
            .with_enabled_packet_diagnostics(packet_collection_enabled)
            .connect(
                user_id=user_id,
                timeout=timeout,
                max_attempts=0 if eflib.is_solar_only(device) else None,
            )
        )
        state = await device.wait_until_authenticated_or_error(raise_on_error=True)
    except (ConnectionTimeout, BleakError, TimeoutError) as e:
        raise ConfigEntryNotReady(
            translation_key="could_not_connect",
            translation_placeholders={"time": str(timeout)},
        ) from e
    except AuthErrors.BaseException as e:
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
        if not state.authenticated:
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


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry to a newer version."""
    _LOGGER.debug(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    match config_entry.version, config_entry.minor_version:
        case 1, 0:
            address = config_entry.data.get(CONF_ADDRESS)
            device_reg = dr.async_get(hass)
            device_entry = device_reg.async_get_device(identifiers={(DOMAIN, address)})

            if device_entry is not None and device_entry.serial_number is not None:
                serial_number = device_entry.serial_number
                old_prefix = device_entry.name + "_"

                entity_reg = er.async_get(hass)
                for entity_entry in er.async_entries_for_config_entry(
                    entity_reg, config_entry.entry_id
                ):
                    old_unique_id = entity_entry.unique_id
                    if old_unique_id.startswith(old_prefix):
                        key = old_unique_id[len(old_prefix) :]
                        new_unique_id = f"ef_{serial_number}_{key}"
                        entity_reg.async_update_entity(
                            entity_entry.entity_id, new_unique_id=new_unique_id
                        )

            hass.config_entries.async_update_entry(config_entry, minor_version=1)

    return True


async def _update_listener(hass: HomeAssistant, entry: DeviceConfigEntry):
    device = entry.runtime_data
    merged_options = entry.data | entry.options
    update_period = merged_options.get(CONF_UPDATE_PERIOD, DEFAULT_UPDATE_PERIOD)
    packet_collection = merged_options.get(
        CONF_COLLECT_PACKETS, eflib.is_unsupported(device)
    )

    (
        device.with_update_period(period=update_period)
        .with_logging_options(ConfLogOptions.from_config(merged_options))
        .with_enabled_packet_diagnostics(packet_collection)
    )

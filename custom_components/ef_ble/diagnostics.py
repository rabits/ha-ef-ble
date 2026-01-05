from homeassistant.core import HomeAssistant

from . import DeviceConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DeviceConfigEntry
):
    device = entry.runtime_data

    diagnostics = {
        "local_name": entry.data.get("local_name", None),
        "device": device.device,
        "name": device.name,
        "default_name": device._default_name,
        "sn_prefix": device._sn[:4],
        "connection_state": device.connection_state,
        "connection_state_history": list(device.connection_log.history),
    }

    if device.diagnostics.is_enabled:
        connection_setup = await hass.async_add_executor_job(
            device.connection_log.load_from_cache
        )
        diagnostics |= device.diagnostics.as_dict()
        diagnostics |= {"connection_setup": connection_setup}

    return diagnostics

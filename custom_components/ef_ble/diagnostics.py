from homeassistant.core import HomeAssistant

from . import DeviceConfigEntry
from .eflib import is_unsupported


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
        "connection_state_history": list(device.state_history),
    }

    if is_unsupported(device):
        diagnostics |= {
            "last_packets": list(device.last_packets),
            "last_packet_errors": list(device.last_errors),
            "last_error": (
                list(device._conn._last_errors) if device._conn is not None else None
            ),
            "diconnect_times": list(device.disconnect_times),
        }

    return diagnostics

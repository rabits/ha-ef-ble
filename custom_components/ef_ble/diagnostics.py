from homeassistant.core import HomeAssistant

from . import DeviceConfigEntry
from .eflib import is_unsupported


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DeviceConfigEntry
):
    device = entry.runtime_data

    if is_unsupported(device):
        return {
            "local_name": entry.data.get("local_name", None),
            "device": device.device,
            "name": device.name,
            "sn_prefix": device._sn[:4],
            "last_xor_payloads": list(device.last_xor_payloads),
            "last_payloads": list(device.last_payloads),
        }

    return {}

from homeassistant.core import HomeAssistant

from . import DeviceConfigEntry
from .const import CONF_DIAGNOSTICS_ENCRYPT, CONF_DIAGNOSTICS_OPTIONS
from .eflib.encryption import Session


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DeviceConfigEntry
):
    device = entry.runtime_data
    diag_options = (entry.data | entry.options).get(CONF_DIAGNOSTICS_OPTIONS, {})
    encrypt = diag_options.get(CONF_DIAGNOSTICS_ENCRYPT, True)

    session = Session() if encrypt else None

    diagnostics = {
        "local_name": entry.data.get("local_name", None),
        "device": device.device,
        "name": device.name,
        "default_name": device._default_name,
        "sn_prefix": device._sn[:4],
        "connection_state": device.connection_state,
        "connection_state_history": list(device.connection_log.history),
        "manufacturer_data": (
            session.encrypt(device._manufacturer_data).hex()
            if session is not None
            else device._manufacturer_data.hex()
        ),
    }

    if session is not None:
        diagnostics["session"] = session.header.hex()

    if device.diagnostics.is_enabled:
        connection_setup = await hass.async_add_executor_job(
            device.connection_log.load_from_cache
        )
        diagnostics |= device.diagnostics.as_dict(session)
        diagnostics |= {"connection_setup": connection_setup}

    return diagnostics

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

    diagnostics: dict = {"local_name": entry.data.get("local_name", None)}
    diagnostics |= device.diagnostics.build_diagnostics_dict(session)

    if device.diagnostics.is_enabled:
        connection_setup = await hass.async_add_executor_job(
            device.connection_log.load_from_cache
        )
        diagnostics |= {"connection_setup": connection_setup}

    return diagnostics

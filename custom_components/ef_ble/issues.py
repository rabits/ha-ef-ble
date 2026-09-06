"""Repair issues this integration raises against a config entry"""

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.issue_registry as ir
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .eflib import device_class_from_sn
from .eflib.device_options import (
    UNLOCK_AC_CHARGING_MINIMUM,
    UNLOCK_DC_CHARGING_MINIMUM,
)

_CHARGING_MINIMUM_OPTIONS = {
    UNLOCK_AC_CHARGING_MINIMUM: ("AC", "W"),
    UNLOCK_DC_CHARGING_MINIMUM: ("DC", "A"),
}


def create_charging_minimum_issue(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    address = config_entry.data.get(CONF_ADDRESS)
    device_entry = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, address)})
    if device_entry is None or not device_entry.serial_number:
        return

    device_class = device_class_from_sn(device_entry.serial_number)
    if device_class is None:
        return

    minimums = device_class.LOCKED_OPTION_VALUES
    # Written as "AC 200 W, DC 4 A" so every translation can name the models' own
    # limits without one sentence per combination of controls a device happens to have
    described = ", ".join(
        f"{label} {minimums[option]} {unit}"
        for option, (label, unit) in _CHARGING_MINIMUM_OPTIONS.items()
        if option in minimums
    )
    if not described:
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{config_entry.entry_id}_charging_minimum_applied",
        is_fixable=False,
        # The migration that raises this never runs again, so it must survive a restart
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="charging_minimum_applied",
        translation_placeholders={
            "device_name": device_entry.name or config_entry.title,
            "minimums": described,
        },
    )

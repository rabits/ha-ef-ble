"""Device triggers for the EcoFlow BLE connection event."""

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)
from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_TYPE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HassJob,
    HomeAssistant,
    callback,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .event import CONNECTION_EVENT_TYPES, is_connection_event

TRIGGER_TYPES = CONNECTION_EVENT_TYPES

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List `connected`/`disconnected` triggers for the device's connection event"""
    registry = er.async_get(hass)
    triggers: list[dict[str, str]] = []
    for entry in er.async_entries_for_device(registry, device_id):
        # A disabled entity has no state to watch, so a trigger built on it would sit
        # there doing nothing; leave it out of the list instead of offering a dud.
        if entry.disabled_by is not None or not is_connection_event(entry):
            continue
        triggers.extend(
            {
                CONF_PLATFORM: "device",
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_ENTITY_ID: entry.id,
                CONF_TYPE: trigger_type,
            }
            for trigger_type in TRIGGER_TYPES
        )
    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """
    Fire when the connection event of the configured type is emitted

    Watches the event entity's state - a timestamp that advances on every emission -
    rather than its `event_type` attribute, so two emissions of the same type in a row
    each fire. Matching on the attribute alone would miss the second one, since the
    attribute would not have changed.
    """
    registry = er.async_get(hass)
    entity_id = er.async_resolve_entity_id(registry, config[CONF_ENTITY_ID])
    entry = registry.async_get(entity_id) if entity_id is not None else None
    if entity_id is None or entry is None:
        raise InvalidDeviceAutomationConfig(
            f"Connection event entity {config[CONF_ENTITY_ID]} no longer exists"
        )
    if entry.disabled_by is not None:
        # Attaching would succeed and then never fire, leaving the automation looking
        # healthy; failing here puts the reason in front of whoever disabled it.
        raise InvalidDeviceAutomationConfig(
            f"Connection event entity {entity_id} is disabled, so it cannot trigger"
        )

    event_type = config[CONF_TYPE]
    job = HassJob(action, f"ef_ble device trigger {entity_id} {event_type}")

    @callback
    def _handle_state_change(event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        if new_state.attributes.get(ATTR_EVENT_TYPE) != event_type:
            return
        if old_state is not None and old_state.state == new_state.state:
            return

        hass.async_run_hass_job(
            job,
            {
                "trigger": {
                    **trigger_info["trigger_data"],
                    CONF_PLATFORM: "device",
                    CONF_DOMAIN: DOMAIN,
                    CONF_DEVICE_ID: config[CONF_DEVICE_ID],
                    CONF_ENTITY_ID: entity_id,
                    CONF_TYPE: event_type,
                    "description": f"{event_type} event on {entity_id}",
                }
            },
            new_state.context,
        )

    return async_track_state_change_event(hass, [entity_id], _handle_state_change)

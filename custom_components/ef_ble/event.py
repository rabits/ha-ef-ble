"""EcoFlow BLE connection event"""

from homeassistant.components.event import ATTR_EVENT_TYPES, EventEntity
from homeassistant.components.event import DOMAIN as EVENT_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceConfigEntry
from .eflib import DeviceBase
from .eflib.connection import ConnectionState
from .entity import EcoflowEntity

EVENT_CONNECTED = "connected"
EVENT_DISCONNECTED = "disconnected"
CONNECTION_EVENT_TYPES = (EVENT_CONNECTED, EVENT_DISCONNECTED)


def is_connection_event(entry: er.RegistryEntry) -> bool:
    """
    Whether a registry entry is a connection event entity of ours

    Matched on the event types the entity registered rather than on its id: an event
    entity that can fire all of `CONNECTION_EVENT_TYPES` is the one a connection trigger
    needs, whatever it ends up being called.
    """
    if entry.domain != EVENT_DOMAIN:
        return False
    event_types = (entry.capabilities or {}).get(ATTR_EVENT_TYPES) or ()
    return set(CONNECTION_EVENT_TYPES).issubset(event_types)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the connection event entity for the config entry"""
    async_add_entities([EcoflowConnectionEvent(config_entry.runtime_data)])


class EcoflowConnectionEvent(EcoflowEntity, EventEntity):
    """
    Fires when the device connection is (re-)established or lost

    Fires on the edges of `authenticated` only, so a reconnect that never reaches a
    terminal state - `AUTHENTICATED` -> `RECONNECTING` -> `AUTHENTICATED`, which is what
    an automatic reconnect looks like - still produces `disconnected` followed by
    `connected`. Being added does not fire anything: an entry reload or a Home Assistant
    restart is not a reconnect, and an automation waiting for one should not run then.
    """

    _attr_translation_key = "connection"
    _attr_event_types = list(CONNECTION_EVENT_TYPES)

    def __init__(self, device: DeviceBase) -> None:
        super().__init__(device)
        self._attr_unique_id = f"ef_{self._device.serial_number}_connection"
        self._remove_listener = None
        self._was_connected: bool | None = None

    @property
    def available(self) -> bool:
        """Keep the event available so its last-fired value survives a reconnect."""
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # A reconnect recreates this entity, so the edge that matters can straddle two
        # instances: seed from the last event this entity fired, not from the live state.
        # Restored `disconnected` means the link dropped while we were gone, so becoming
        # authenticated now is a real reconnect and fires; restored `connected` means a
        # restart or reload of a healthy link and stays quiet.
        restored = await self.async_get_last_event_data()
        self._was_connected = (
            restored is not None and restored.last_event_type == EVENT_CONNECTED
        )
        self._remove_listener = self._device.on_connection_state_change(
            self._on_connection_state_change
        )
        state = self._device.connection_state
        if state is not None:
            self._on_connection_state_change(state)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        await super().async_will_remove_from_hass()

    @callback
    def _on_connection_state_change(self, state: ConnectionState) -> None:
        # Every state that is not `authenticated` counts as disconnected, including the
        # intermediate ones a reconnect passes through; only the transition fires.
        is_connected = state.authenticated
        if is_connected == self._was_connected:
            return
        self._was_connected = is_connected
        self._fire(EVENT_CONNECTED if is_connected else EVENT_DISCONNECTED)

    def _fire(self, event_type: str) -> None:
        self._trigger_event(event_type)
        self.async_write_ha_state()

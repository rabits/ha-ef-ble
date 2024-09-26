"""EcoFlow BLE binary sensor"""

import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add binary sensors for passed config_entry in HA."""
    device = config_entry.runtime_data

    new_sensors = []
    if hasattr(device, 'error_happened'):
        new_sensors.append(ErrorDetectedSensor(device))

    if new_sensors:
        async_add_entities(new_sensors)

class SensorBase(Entity):
    """Base representation of a binary sensor."""

    def __init__(self, device):
        """Initialize the sensor."""
        self._device = device

    @property
    def device_info(self):
        """Return information to link this entity with the correct device."""
        return {"identifiers": {(DOMAIN, self._device.address)}}

    @property
    def available(self) -> bool:
        """Return True if device is connected."""
        return self._device.is_connected

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""
        self._device.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        self._device.remove_callback(self.async_write_ha_state)

class ErrorDetectedSensor(SensorBase):
    """Represents that problem happened on device."""

    device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_error"

        self._attr_name = "Error"

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        if self._device.error_happened:
            return True
        return False

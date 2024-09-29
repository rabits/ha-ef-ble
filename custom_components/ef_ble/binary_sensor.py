"""EcoFlow BLE binary sensor"""

import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceConfigEntry
from .sensor import SensorBase
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

class ErrorDetectedSensor(SensorBase):
    """Represents that problem happened on device."""

    device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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

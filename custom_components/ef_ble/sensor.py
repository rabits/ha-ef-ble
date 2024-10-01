"""EcoFlow BLE sensor"""

import random
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfElectricCurrent,
)

from . import DeviceConfigEntry
from .const import DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    device = config_entry.runtime_data

    new_sensors = []
    if hasattr(device, 'battery_level'):
        new_sensors.append(BatterySensor(device))
    if hasattr(device, 'circuit_power'):
        for i in range(len(device.circuit_power)):
            new_sensors.append(CircuitPowerSensor(device, i))
    if hasattr(device, 'circuit_current'):
        for i in range(len(device.circuit_current)):
            new_sensors.append(CircuitCurrentSensor(device, i))
    if hasattr(device, 'grid_power'):
        new_sensors.append(GridPowerSensor(device))
    if hasattr(device, 'in_use_power'):
        new_sensors.append(InUsePowerSensor(device))
    if hasattr(device, 'channel_power'):
        for i in range(len(device.channel_power)):
            new_sensors.append(ChannelPowerSensor(device, i))

    if new_sensors:
        async_add_entities(new_sensors)

class SensorBase(SensorEntity):
    """Base representation of a sensor."""

    _attr_has_entity_name = True

    def __init__(self, device):
        """Initialize the sensor."""
        self._device = device

    @property
    def device_info(self):
        """Return information to link this entity with the correct device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.address)},
            name=self._device.name,
            manufacturer=MANUFACTURER,
            model=self._device.device,
        )

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

class BatterySensor(SensorBase):
    """Shows total battery level of a device."""

    device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_battery"
        self._attr_name = "Battery"

    @property
    def native_value(self) -> int:
        """Return the value of the sensor."""
        return self._device.battery_level

class CircuitPowerSensor(SensorBase):
    """Represents circuit consumed wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 2

    def __init__(self, device, index):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_circuit_power_{index+1}"
        self._attr_name = f"Circuit Power {index+1}"
        self._index = index

    @property
    def native_value(self) -> float:
        """Return the value of the sensor."""
        return self._device.circuit_power[self._index]

class CircuitCurrentSensor(SensorBase):
    """Represents circuit consumed amperage."""

    device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 2

    def __init__(self, device, index):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_circuit_current_{index+1}"
        self._attr_name = f"Circuit Current {index+1}"
        self._index = index

    @property
    def native_value(self) -> float:
        """Return the value of the sensor."""
        return self._device.circuit_current[self._index]

class GridPowerSensor(SensorBase):
    """Represents grid intake wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_grid_power"
        self._attr_name = "Grid Power"

    @property
    def native_value(self) -> float:
        """Return the value of the sensor."""
        return self._device.grid_power

class InUsePowerSensor(SensorBase):
    """Represents in use wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:home-lightning-bolt-outline"

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_in_use_power"
        self._attr_name = "In Use Power"

    @property
    def native_value(self) -> float:
        """Return the value of the sensor."""
        return self._device.in_use_power

class ChannelPowerSensor(SensorBase):
    """Represents backup channel wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 2

    def __init__(self, device, index):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_channel_power_{index+1}"
        self._attr_name = f"Channel Power {index+1}"
        self._index = index

    @property
    def native_value(self) -> float:
        """Return the value of the sensor."""
        return self._device.channel_power[self._index]

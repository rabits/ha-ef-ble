"""EcoFlow BLE sensor"""

import random

from homeassistant.components.sensor import SensorDeviceClass

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfElectricCurrent,
)

from . import DeviceConfigEntry
from .const import DOMAIN

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
    if hasattr(device, 'breaker_power'):
        for i in range(len(device.breaker_power)):
            new_sensors.append(BreakerPowerSensor(device, i))
    if hasattr(device, 'breaker_current'):
        for i in range(len(device.breaker_current)):
            new_sensors.append(BreakerCurrentSensor(device, i))
    if hasattr(device, 'grid_power'):
        new_sensors.append(GridPowerSensor(device))
    if hasattr(device, 'in_use_power'):
        new_sensors.append(InUsePowerSensor(device))
    if hasattr(device, 'channel_power'):
        for i in range(len(device.channel_power)):
            new_sensors.append(ChannelPowerSensor(device, i))

    if new_sensors:
        async_add_entities(new_sensors)

class SensorBase(Entity):
    """Base representation of a sensor."""

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

class BatterySensor(SensorBase):
    """Shows total battery level of a device."""

    device_class = SensorDeviceClass.BATTERY
    _attr_unit_of_measurement = PERCENTAGE

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_battery"

        self._attr_name = f"Battery"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._device.battery_level

class BreakerPowerSensor(SensorBase):
    """Represents breaker consumed wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, device, index):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_breaker_power_{index+1}"

        self._attr_name = f"Breaker Power {index+1}"

        self._index = index

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._device.breaker_power[self._index]

class BreakerCurrentSensor(SensorBase):
    """Represents breaker consumed amperage."""

    device_class = SensorDeviceClass.CURRENT
    _attr_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 2

    def __init__(self, device, index):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_breaker_current_{index+1}"

        self._attr_name = f"Breaker Current {index+1}"

        self._index = index

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._device.breaker_current[self._index]

class GridPowerSensor(SensorBase):
    """Represents grid intake wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_grid_power"

        self._attr_name = "Grid Power"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._device.grid_power

class InUsePowerSensor(SensorBase):
    """Represents in use wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_in_use_power"

        self._attr_name = "In Use Power"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._device.in_use_power

class ChannelPowerSensor(SensorBase):
    """Represents backup channel wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, device, index):
        """Initialize the sensor."""
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_channel_power_{index+1}"

        self._attr_name = f"Channel Power {index+1}"

        self._index = index

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._device.channel_power[self._index]
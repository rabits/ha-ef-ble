"""EcoFlow BLE sensor"""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ef_ble.eflib import DeviceBase

from . import DeviceConfigEntry
from .entity import EcoflowEntity

SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    # Common
    "battery_level": SensorEntityDescription(
        key="battery_level",
        name="Battery Level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "battery_level_main": SensorEntityDescription(
        key="battery_level_main",
        name="Main Battery Level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "input_power": SensorEntityDescription(
        key="input_power",
        name="Input Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:home-lightning-bolt-outline",
    ),
    "output_power": SensorEntityDescription(
        key="output_power",
        name="Output Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:home-lightning-bolt-outline",
    ),
    # SHP2
    "grid_power": SensorEntityDescription(
        key="grid_power",
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:transmission-tower",
    ),
    "in_use_power": SensorEntityDescription(
        key="in_use_power",
        name="In Use Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:home-lightning-bolt-outline",
    ),
    # DPU
    "lv_solar_power": SensorEntityDescription(
        key="lv_solar_power",
        name="LV Solar Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:solar-panel",
    ),
    "hv_solar_power": SensorEntityDescription(
        key="hv_solar_power",
        name="HV Solar Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:solar-panel-large",
    ),
    # River 3, Delta 3
    "input_energy": SensorEntityDescription(
        key="input_energy",
        name="Input Energy Total",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "output_energy": SensorEntityDescription(
        key="output_energy",
        name="Output Energy Total",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "ac_input_power": SensorEntityDescription(
        key="ac_input_power",
        name="AC Input Power",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "ac_output_power": SensorEntityDescription(
        key="ac_output_power",
        name="AC Output Power",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "ac_input_energy": SensorEntityDescription(
        key="ac_input_energy",
        name="AC Input Energy",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "ac_output_energy": SensorEntityDescription(
        key="ac_output_energy",
        name="AC Output Energy",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "dc_input_power": SensorEntityDescription(
        key="dc_input_power",
        name="DC Input Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "dc_input_energy": SensorEntityDescription(
        key="dc_input_energy",
        name="DC Input Energy",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "dc12v_output_power": SensorEntityDescription(
        key="dc12v_output_power",
        name="DC 12V Output Power",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "dc12v_output_energy": SensorEntityDescription(
        key="dc12v_output_energy",
        name="DC 12V Output Energy",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "usbc_output_power": SensorEntityDescription(
        key="usbc_output_power",
        name="USB C Output Power",
        icon="mdi:usb-c-port",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "usbc_output_energy": SensorEntityDescription(
        key="usbc_output_energy",
        name="USB C Output Energy",
        icon="mdi:usb-c-port",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "usba_output_power": SensorEntityDescription(
        key="usba_output_power",
        name="USB A Output Power",
        icon="mdi:usb-port",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "usba_output_energy": SensorEntityDescription(
        key="usba_output_energy",
        name="USB A Output Energy",
        icon="mdi:usb-port",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "usbc2_output_power": SensorEntityDescription(
        key="usbc2_output_power",
        name="USB C (2) Output Power",
        icon="mdi:usb-c-port",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "usba2_output_power": SensorEntityDescription(
        key="usba2_output_power",
        name="USB A (2) Output Power",
        icon="mdi:usb-port",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "battery_input_power": SensorEntityDescription(
        key="battery_input_power",
        name="Battery Input Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "battery_output_power": SensorEntityDescription(
        key="battery_output_power",
        name="Battery Output Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "cell_temperature": SensorEntityDescription(
        key="temperature",
        name="Cell Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
    ),
    "dc_port_input_power": SensorEntityDescription(
        key="dc_port_input_power",
        name="DC Port Input Power",
        icon="mdi:current-dc",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=2,
    ),
    "dc_port_2_input_power": SensorEntityDescription(
        key="dc_port_input_power_2",
        name="DC Port (2) Input Power",
        icon="mdi:current-dc",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=2,
    ),
    "dc_port_state": SensorEntityDescription(
        key="dc_port_1_state",
        name="DC Input Port State",
        icon="mdi:current-dc",
        device_class=SensorDeviceClass.ENUM,
    ),
    "dc_port_2_state": SensorEntityDescription(
        key="dc_port_2_state",
        name="DC Input Port (2) State ",
        icon="mdi:current-dc",
        device_class=SensorDeviceClass.ENUM,
    ),
    "solar_input_power": SensorEntityDescription(
        key="input_power_solar",
        name="Solar Power",
        icon="mdi:solar-power-variant-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "solar_input_power_2": SensorEntityDescription(
        key="input_power_solar_2",
        name="Solar Power (2)",
        icon="mdi:solar-power-variant-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    device = config_entry.runtime_data

    new_sensors = [
        EcoflowSensor(device, sensor)
        for sensor in SENSOR_TYPES
        if hasattr(device, sensor)
    ]

    # SHP2 sensors
    if hasattr(device, "circuit_power"):
        for i in range(len(device.circuit_power)):
            new_sensors.append(CircuitPowerSensor(device, i))
    if hasattr(device, "circuit_current"):
        for i in range(len(device.circuit_current)):
            new_sensors.append(CircuitCurrentSensor(device, i))
    if hasattr(device, "channel_power"):
        for i in range(len(device.channel_power)):
            new_sensors.append(ChannelPowerSensor(device, i))

    if new_sensors:
        async_add_entities(new_sensors)


class EcoflowSensor(EcoflowEntity, SensorEntity):
    """Base representation of a sensor."""

    def __init__(self, device: DeviceBase, sensor: str):
        """Initialize the sensor."""
        super().__init__(device)

        self._sensor = sensor
        self._attr_unique_id = f"{device.name}_{sensor}"

        if sensor in SENSOR_TYPES:
            self.entity_description = SENSOR_TYPES[sensor]
        else:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the value of the sensor."""
        return getattr(self._device, self._sensor, None)

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""
        self._device.register_callback(self.async_write_ha_state, self._sensor)

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        self._device.remove_callback(self.async_write_ha_state, self._sensor)


class CircuitPowerSensor(EcoflowSensor):
    """Represents circuit consumed wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 2

    def __init__(self, device, index):
        """Initialize the sensor."""
        super().__init__(device, f"circuit_power_{index}")

        self._attr_unique_id = f"{self._device.name}_circuit_power_{index + 1}"
        self._attr_name = f"Circuit Power {index + 1:02d}"
        self._index = index

    @property
    def native_value(self) -> float:
        """Return the value of the sensor."""
        return self._device.circuit_power[self._index]


class CircuitCurrentSensor(EcoflowSensor):
    """Represents circuit consumed amperage."""

    device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 2
    _attr_entity_registry_enabled_default = False

    def __init__(self, device, index):
        """Initialize the sensor."""
        super().__init__(device, f"circuit_current_{index}")

        self._attr_unique_id = f"{self._device.name}_circuit_current_{index + 1}"
        self._attr_name = f"Circuit Current {index + 1:02d}"
        self._index = index

    @property
    def native_value(self) -> float:
        """Return the value of the sensor."""
        return self._device.circuit_current[self._index]


class ChannelPowerSensor(EcoflowSensor):
    """Represents backup channel wattage."""

    device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 2

    def __init__(self, device, index):
        """Initialize the sensor."""
        super().__init__(device, f"channel_power_{index}")

        self._attr_unique_id = f"{self._device.name}_channel_power_{index + 1}"
        self._attr_name = f"Channel Power {index + 1}"
        self._index = index

    @property
    def native_value(self) -> float:
        """Return the value of the sensor."""
        return self._device.channel_power[self._index]

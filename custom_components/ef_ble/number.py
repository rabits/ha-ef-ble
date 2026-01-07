from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceConfigEntry
from .eflib import DeviceBase
from .eflib.devices import (
    alternator_charger,
    delta3_classic,
    delta3_plus,
    delta_pro_3,
    river3,
    smart_generator,
    smart_generator_4k,
    stream_ac,
    wave2,
)
from .entity import EcoflowEntity


@dataclass(frozen=True, kw_only=True)
class EcoflowNumberEntityDescription[Device: DeviceBase](NumberEntityDescription):
    async_set_native_value: Callable[[Device, float], Awaitable[bool]] | None = None

    min_value_prop: str | None = None
    max_value_prop: str | None = None
    availability_prop: str | None = None


NUMBER_TYPES: list[EcoflowNumberEntityDescription] = [
    EcoflowNumberEntityDescription[river3.Device](
        key="energy_backup_battery_level",
        name="Backup Reserve",
        icon="mdi:battery-sync",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        min_value_prop="battery_charge_limit_min",
        max_value_prop="battery_charge_limit_max",
        async_set_native_value=(
            lambda device, value: device.set_energy_backup_battery_level(int(value))
        ),
        availability_prop="energy_backup",
    ),
    EcoflowNumberEntityDescription[river3.Device](
        key="battery_charge_limit_min",
        name="Discharge Limit",
        icon="mdi:battery-arrow-down-outline",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        native_min_value=0,
        max_value_prop="battery_charge_limit_max",
        async_set_native_value=(
            lambda device, value: device.set_battery_charge_limit_min(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[river3.Device](
        key="battery_charge_limit_max",
        name="Charge Limit",
        icon="mdi:battery-arrow-up",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        native_max_value=100,
        min_value_prop="battery_charge_limit_min",
        async_set_native_value=(
            lambda device, value: device.set_battery_charge_limit_max(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[
        river3.Device | delta3_classic.Device | delta_pro_3.Device
    ](
        key="ac_charging_speed",
        name="AC Charging Speed",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="max_ac_charging_power",
        async_set_native_value=(
            lambda device, value: device.set_ac_charging_speed(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[river3.Device | delta3_classic.Device](
        key="dc_charging_max_amps",
        name="DC Charging Max Amps",
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_step=1,
        native_min_value=0,
        max_value_prop="dc_charging_current_max",
        async_set_native_value=(
            lambda device, value: device.set_dc_charging_amps_max(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[delta3_plus.Device](
        key="dc_charging_max_amps_2",
        name="DC (2) Charging Max Amps",
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_step=1,
        native_min_value=0,
        max_value_prop="dc_charging_current_max_2",
        async_set_native_value=(
            lambda device, value: device.set_dc_charging_amps_max_2(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[smart_generator.Device](
        key="liquefied_gas_value",
        name="Gas Weight",
        native_min_value=0,
        native_step=0.1,
        availability_prop="lpg_level_monitoring",
        mode=NumberMode.BOX,
        async_set_native_value=(
            lambda device, value: device.set_liquefied_gas_value(value)
        ),
    ),
    EcoflowNumberEntityDescription[smart_generator_4k.Device](
        key="dc_output_power_limit",
        name="DC Power Limit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        mode=NumberMode.SLIDER,
        native_step=100,
        min_value_prop="dc_output_power_min",
        max_value_prop="dc_output_power_max",
        async_set_native_value=(
            lambda device, value: device.set_dc_output_power_max(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[alternator_charger.Device](
        key="power_limit",
        name="Power Limit",
        max_value_prop="power_max",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        async_set_native_value=(
            lambda device, value: device.set_power_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="feed_grid_pow_limit",
        name="Feed Grid Power Limit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="feed_grid_pow_max",
        async_set_native_value=(
            lambda device, value: device.set_feed_grid_pow_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[alternator_charger.Device](
        key="start_voltage",
        name="Start Voltage",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_step=0.1,
        min_value_prop="start_voltage_min",
        max_value_prop="start_voltage_max",
        async_set_native_value=(
            lambda device, value: device.set_battery_voltage(value)
        ),
    ),
    EcoflowNumberEntityDescription[alternator_charger.Device](
        key="reverse_charging_current_limit",
        name="Reverse Charging Current",
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_step=0.1,
        native_min_value=0,
        max_value_prop="reverse_charging_current_max",
        async_set_native_value=(
            lambda device, value: device.set_car_battery_curent_charge_limit(value)
        ),
    ),
    EcoflowNumberEntityDescription[alternator_charger.Device](
        key="charging_current_limit",
        name="Charging Current",
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_step=1,
        native_min_value=0,
        max_value_prop="charging_current_max",
        async_set_native_value=(
            lambda device, value: device.set_device_battery_current_charge_limit(value)
        ),
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="feed_grid_pow_limit",
        name="Feed Grid Power Limit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="feed_grid_pow_max",
        async_set_native_value=(
            lambda device, value: device.set_feed_grid_pow_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="base_load_power",
        name="Base Load Power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="feed_grid_pow_max",
        async_set_native_value=(
            lambda device, value: device.set_load_power(int(value))
        ),
        availability_prop="load_power_enabled",
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="grid_in_power_limit",
        name="Grid Input Power Limit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="max_ac_in_power",
        async_set_native_value=(
            lambda device, value: device.set_grid_in_pow_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="charging_grid_power_limit",
        name="Charging Power Limit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="max_bp_input",
        async_set_native_value=(
            lambda device, value: device.set_charging_grid_power_limit(int(value))
        ),
        availability_prop="charging_grid_power_limit_enabled",
    ),
    EcoflowNumberEntityDescription[wave2.Device](
        key="target_temperature",
        name="Temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_step=1,
        native_min_value=16,
        native_max_value=30,
        async_set_native_value=(
            lambda device, value: device.set_temperature(int(value))
        ),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device = config_entry.runtime_data

    async_add_entities(
        [
            EcoflowNumber(device, entity_description)
            for entity_description in NUMBER_TYPES
            if hasattr(device, entity_description.key)
        ]
    )


class EcoflowNumber(EcoflowEntity, NumberEntity):
    def __init__(
        self,
        device: DeviceBase,
        entity_description: EcoflowNumberEntityDescription[DeviceBase],
    ):
        super().__init__(device)
        self._attr_unique_id = f"{device.name}_{entity_description.key}"
        self.entity_description = entity_description
        self._min_value_prop = entity_description.min_value_prop
        self._max_value_prop = entity_description.max_value_prop
        self._availability_prop = entity_description.availability_prop
        self._set_native_value = entity_description.async_set_native_value
        self._prop_name = entity_description.key
        self._attr_native_value = getattr(device, self._prop_name)

        if entity_description.translation_key is None:
            self._attr_translation_key = self.entity_description.key

        if entity_description.translation_key is None:
            self._attr_translation_key = self.entity_description.key

        self._register_update_callback("_attr_native_value", self._prop_name)
        self._register_update_callback(
            "_attr_available",
            self._availability_prop,
            lambda state: state if state is not None else False,
        )
        self._register_update_callback(
            "_attr_native_min_value",
            self._min_value_prop,
            lambda state: state if state is not None else self.SkipWrite,
        )
        self._register_update_callback(
            "_attr_native_max_value",
            self._max_value_prop,
            lambda state: state if state is not None else self.SkipWrite,
        )

    @property
    def available(self):
        is_available = super().available
        if not is_available or self._availability_prop is None:
            return is_available

        return self._attr_available

    async def async_set_native_value(self, value: float) -> None:
        if self._set_native_value is not None:
            await self._set_native_value(self._device, value)
            return

        await super().async_set_native_value(value)

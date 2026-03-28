import dataclasses
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
    UnitOfMass,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceConfigEntry
from .description_builder import EntityDescriptionBuilder, unit_to_hassunit
from .eflib import DeviceBase, controls, get_controls
from .eflib.devices import (
    alternator_charger,
    delta3_classic,
    delta3_plus,
    delta_pro_3,
    dpu,
    powerstream,
    river2,
    river3,
    shp2,
    smart_generator,
    smart_generator_4k,
    stream_ac,
    stream_microinverter,
    wave2,
)
from .eflib.props import Field
from .entity import EcoflowEntity


@dataclass(frozen=True, kw_only=True)
class EcoflowNumberEntityDescription[Device: DeviceBase](NumberEntityDescription):
    async_set_native_value: Callable[[Device, float], Awaitable[bool]] | None = None

    min_value_prop: str | None = None
    max_value_prop: str | None = None
    step_value_prop: str | None = None
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
        river3.Device
        | delta3_classic.Device
        | delta_pro_3.Device
        | river2.Device
        | shp2.Device
    ](
        key="ac_charging_speed",
        name="AC Charging Speed",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        step_value_prop="ac_charging_speed_step",
        min_value_prop="min_ac_charging_power",
        max_value_prop="max_ac_charging_power",
        async_set_native_value=(
            lambda device, value: device.set_ac_charging_speed(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[
        river3.Device | delta3_classic.Device | river2.Device
    ](
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
    EcoflowNumberEntityDescription[powerstream.Device](
        key="load_power",
        name="Load Power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=0.1,
        native_min_value=0,
        max_value_prop="load_power_max",
        async_set_native_value=lambda device, value: device.set_load_power(value),
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
        native_step=100,
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
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="charging_grid_target_soc",
        name="Charging Target SOC",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        async_set_native_value=(
            lambda device, value: device.set_charging_grid_target_soc(int(value))
        ),
        availability_prop="charging_grid_power_limit_enabled",
    ),
    EcoflowNumberEntityDescription[stream_microinverter.Device](
        key="feed_grid_mode_power_limit",
        name="Maximum Output Power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="feed_grid_mode_power_max",
        async_set_native_value=(
            lambda device, value: device.set_feed_grid_mode_pow_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device | shp2.Device](
        key="backup_reserve_level",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        min_value_prop="backup_reserve_level_min",
        max_value_prop="backup_reserve_level_max",
        availability_prop="backup_reserve_level_availability",
        async_set_native_value=(
            lambda device, value: device.set_backup_reserve_level(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device](
        key="backup_discharge_limit",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        min_value_prop="backup_discharge_limit_min",
        max_value_prop="backup_discharge_limit_max",
        async_set_native_value=(
            lambda device, value: device.set_backup_discharge_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device | shp2.Device](
        key="backup_charge_limit",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        min_value_prop="backup_charge_limit_min",
        max_value_prop="backup_charge_limit_max",
        availability_prop="backup_charge_limit_availability",
        async_set_native_value=(
            lambda device, value: device.set_backup_charge_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device](
        key="ac_5p8_charging_power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=100,
        min_value_prop="ac_5p8_min_charging_power",
        max_value_prop="ac_5p8_max_charging_power",
        async_set_native_value=(
            lambda device, value: device.set_ac_5p8_charging_power(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device](
        key="ac_c20_charging_power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=100,
        min_value_prop="ac_c20_min_charging_power",
        max_value_prop="ac_c20_max_charging_power",
        availability_prop="ac_c20_charging_power_availability",
        async_set_native_value=(
            lambda device, value: device.set_ac_c20_charging_power(int(value))
        ),
    ),
]


def _liquefied_gas_unit(dev: DeviceBase) -> str:
    unit = getattr(dev, "liquefied_gas_unit", None)
    if (
        unit is not None
        and getattr(unit, "value", -1) == smart_generator.LiquefiedGasUnit.LB.value
    ):
        return UnitOfMass.POUNDS
    return UnitOfMass.KILOGRAMS


@dataclass(init=False)
class NumberSensorBuilder(EntityDescriptionBuilder):
    _native_unit_of_measurement: str | None = None
    _native_min_value: float | None = None
    _native_max_value: float | None = None
    _min_value_prop: str | None = None
    _max_value_prop: str | None = None
    _native_step: float | None = None
    _async_set_native_value: Callable[[DeviceBase, float], Awaitable[bool]] | None = (
        None
    )
    _device_class: NumberDeviceClass | None = None
    _native_unit_of_measurement_field: Callable[[DeviceBase], str] | None = None

    def device_class(self, device_class: NumberDeviceClass):
        self._device_class = device_class
        return self

    def native_unit_of_measurement(self, unit: str):
        self._native_unit_of_measurement = unit_to_hassunit(unit)
        return self

    def native_step(self, step: float):
        self._native_step = step
        return self

    def native_min_value(self, min_value: float | Field):
        if field := self._get_field(min_value):
            self._min_value_prop = field.public_name
            return self
        self._native_min_value = min_value
        return self

    def native_max_value(self, max_value: float | Field | None):
        if field := self._get_field(max_value):
            self._max_value_prop = field.public_name
            return self
        self._native_max_value = max_value
        return self

    def availability_prop(self, availability_prop: str | Field):
        if field := self._get_field(availability_prop):
            self._availability_prop = field.public_name
            return self
        self._availability_prop = availability_prop
        return self

    def native_unit_of_measurement_field(self, func: Callable[[DeviceBase], str]):
        self._native_unit_of_measurement_field = func
        return self

    def async_set_native_value(
        self, func: Callable[[DeviceBase, float], Awaitable[bool]]
    ):
        self._async_set_native_value = func
        return self

    def build(self):
        return EcoflowNumberEntityDescription(
            key=self._entity_key,
            name=self._entity_name,
            device_class=self._device_class,
            native_unit_of_measurement=self._native_unit_of_measurement,
            async_set_native_value=self._async_set_native_value,
            native_min_value=self._native_min_value,
            native_max_value=self._native_max_value,
            min_value_prop=self._min_value_prop,
            max_value_prop=self._max_value_prop,
            native_step=self._native_step,
            native_unit_of_measurement_field=self._native_unit_of_measurement_field,
            translation_key=self._entity_translation_key,
            entity_registry_enabled_default=self._entity_registry_enabled_default,
            icon=self._icon,
            availability_prop=self._availability_prop,
        )


@dataclasses.dataclass
class _Builder[E: controls.NumberType]:
    builder: Callable[[E, NumberSensorBuilder], NumberSensorBuilder]


_BUILDERS: dict[type[controls.NumberType], _Builder] = {
    controls.power: _Builder[controls.power](
        lambda number, builder: (
            builder.device_class(NumberDeviceClass.POWER).native_unit_of_measurement(
                number.unit
            )
        )
    ),
    controls.battery: _Builder[controls.battery](
        lambda number, builder: (
            builder.device_class(NumberDeviceClass.BATTERY).native_unit_of_measurement(
                PERCENTAGE
            )
        )
    ),
    controls.current: _Builder[controls.current](
        lambda number, builder: (
            builder.device_class(NumberDeviceClass.CURRENT).native_unit_of_measurement(
                number.unit
            )
        ),
    ),
    controls.temperature: _Builder[controls.temperature](
        lambda number, builder: (
            builder.device_class(
                NumberDeviceClass.TEMPERATURE
            ).native_unit_of_measurement(number.unit)
        ),
    ),
    controls.weight: _Builder[controls.weight](
        lambda number, builder: (
            builder.device_class(
                NumberDeviceClass.WEIGHT
            ).native_unit_of_measurement_field(_liquefied_gas_unit)
        )
    ),
}


def _build_control_numbers(
    device: DeviceBase,
) -> list[EcoflowNumberEntityDescription]:
    return [
        (
            _BUILDERS[number.__class__]
            .builder(number, NumberSensorBuilder.from_entity(number))
            .native_min_value(number.min)
            .native_max_value(number.max)
            .native_step(number.step)
            .availability_prop(number.availability_prop)
            .async_set_native_value(number.set_value_func)
            .build()
        )
        for number in get_controls(device, control_type=controls.NumberType)
        if number.__class__ in _BUILDERS and number.set_value_func is not None
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device = config_entry.runtime_data

    # New controls system (devices migrated to @controls decorators)
    control_descs = _build_control_numbers(device)
    control_keys = {d.key for d in control_descs}

    # Deprecated: old hardcoded list (for devices not yet migrated)
    legacy_descs = [
        desc
        for desc in NUMBER_TYPES
        if desc.key not in control_keys and hasattr(device, desc.key)
    ]

    entities = [EcoflowNumber(device, desc) for desc in [*control_descs, *legacy_descs]]
    if entities:
        async_add_entities(entities)


class EcoflowNumber(EcoflowEntity, NumberEntity):
    def __init__(
        self,
        device: DeviceBase,
        entity_description: EcoflowNumberEntityDescription[DeviceBase],
    ):
        super().__init__(device)
        self._attr_unique_id = f"ef_{device.serial_number}_{entity_description.key}"
        self.entity_description = entity_description
        self._min_value_prop = entity_description.min_value_prop
        self._max_value_prop = entity_description.max_value_prop
        self._step_value_prop = getattr(entity_description, "step_value_prop", None)
        self._availability_prop = entity_description.availability_prop
        self._set_native_value = entity_description.async_set_native_value
        self._prop_name = entity_description.key
        self._attr_native_value = getattr(device, self._prop_name)

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
            0,
        )
        self._register_update_callback(
            "_attr_native_max_value",
            self._max_value_prop,
            lambda state: state if state is not None else self.SkipWrite,
        )

        self._register_update_callback(
            "_attr_native_step",
            self._step_value_prop,
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

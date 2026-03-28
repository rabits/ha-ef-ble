import dataclasses
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfMass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceConfigEntry
from .deprecated.numbers import NUMBER_TYPES
from .description_builder import EntityDescriptionBuilder, unit_to_hassunit
from .eflib import DeviceBase, controls, get_controls
from .eflib.devices import smart_generator
from .eflib.props import Field
from .entity import EcoflowEntity


@dataclass(frozen=True, kw_only=True)
class EcoflowNumberEntityDescription[Device: DeviceBase](NumberEntityDescription):
    async_set_native_value: Callable[[Device, float], Awaitable[bool]] | None = None
    native_unit_of_measurement_field: Callable[[Device], str] | None = None

    min_value_prop: str | None = None
    max_value_prop: str | None = None
    step_value_prop: str | None = None
    availability_prop: str | None = None


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


def _liquefied_gas_unit(dev: DeviceBase) -> str:
    unit = getattr(dev, "liquefied_gas_unit", None)
    if (
        unit is not None
        and getattr(unit, "value", -1) == smart_generator.LiquefiedGasUnit.LB.value
    ):
        return UnitOfMass.POUNDS
    return UnitOfMass.KILOGRAMS


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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device = config_entry.runtime_data

    # New controls system (devices migrated to @controls decorators)
    descriptions = [
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
    ]

    if not descriptions:
        # Deprecated: old hardcoded list (for devices not yet migrated)
        descriptions = [desc for desc in NUMBER_TYPES if hasattr(device, desc.key)]

    entities = [EcoflowNumber(device, desc) for desc in descriptions]
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
        self._native_unit_of_measurement_field = (
            entity_description.native_unit_of_measurement_field
        )
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
    def native_unit_of_measurement(self) -> str | None:
        if (unit_func := self._native_unit_of_measurement_field) is not None:
            return unit_func(self._device)
        return super().native_unit_of_measurement

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

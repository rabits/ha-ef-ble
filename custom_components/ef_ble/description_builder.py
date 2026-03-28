from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Self

from homeassistant.components.select import SelectEntityDescription
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTemperature,
)

from .eflib import DeviceBase, units
from .eflib.entity import DynamicValue, EntityType
from .eflib.props import Field

_UPPER_WORDS = ["ac", "dc"]


@dataclass(init=False)
class EntityDescriptionBuilder:
    field: "Field | None"

    _name: str | None = None
    _key: str | None = None
    _icon: str | None = None
    _entity_category: EntityCategory | None = None
    _translation_key: str | None = None
    _translation_placeholders: dict[str, str] | None = None
    _availability_prop: str | None = None
    _entity_registry_enabled_default: bool = True

    @classmethod
    def from_entity(cls, entity: EntityType):
        obj = cls()
        obj.field = entity.field
        builder = obj.key(entity.key).enabled(entity.enabled)
        if entity.translation_key is not None:
            builder = builder.translation_key(entity.translation_key)
        if entity.translation_placeholders is not None:
            builder = builder.translation_placeholders(entity.translation_placeholders)
        if entity.availability is not None:
            builder = builder.availability_prop(entity.availability_prop)
        return builder

    def name(self, name: str) -> Self:
        self._name = name
        return self

    def key(self, key: str) -> Self:
        self._key = key
        return self

    def icon(self, icon: str):
        self._icon = icon
        return self

    def enabled(self, enabled: bool = True):
        self._entity_registry_enabled_default = enabled
        return self

    def translation_key(self, translation_key: str) -> Self:
        self._translation_key = translation_key
        return self

    def translation_placeholders(self, placeholders: dict[str, str]) -> Self:
        self._translation_placeholders = placeholders
        return self

    def availability_prop(self, availability_prop: "str | Field | None") -> Self:
        if field := self._get_field(availability_prop):
            self._availability_prop = field.public_name
        else:
            self._availability_prop = availability_prop  # type: ignore[assignment]
        return self

    def entity_category(self, entity_category: EntityCategory):
        self._entity_category = entity_category
        return self

    def _get_field(self, val: Any):
        match val:
            case Field():
                return val
            case DynamicValue():
                return val.field
            case _:
                return None

    @property
    def _field(self) -> "Field":
        return self.field  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def _entity_key(self):
        if self._key is not None:
            return self._key

        if self._field is None:
            raise ValueError("Cannot create sensor key without field")

        return self._field.public_name

    @property
    def _entity_name(self):
        if self._name is not None:
            return self._name

        if self._field is None:
            raise ValueError("Cannot create default sensor name without field")

        return " ".join(
            [
                word.upper() if word in _UPPER_WORDS else word.capitalize()
                for word in self._entity_key.split("_")
            ]
        )

    @property
    def _entity_translation_key(self):
        if self._translation_key is not None:
            return self._translation_key

        if self._field is None:
            raise ValueError("Cannot create default translation key without field")

        return self._entity_key


@dataclass(kw_only=True, frozen=True)
class EcoflowSelectEntityDescription[T: DeviceBase](SelectEntityDescription):
    set_state: Callable[[T, str], Awaitable] | None = None

    availability_prop: str | None = None


_UNIT_CONVERSION = {
    units.Power.WATT: UnitOfPower.WATT,
    units.Temperature.C: UnitOfTemperature.CELSIUS,
    units.Temperature.F: UnitOfTemperature.FAHRENHEIT,
    units.Current.AMPERE: UnitOfElectricCurrent.AMPERE,
}


def unit_to_hassunit(unit: str | units.Unit):
    return _UNIT_CONVERSION.get(unit, unit)

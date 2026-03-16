import dataclasses
from collections.abc import Callable
from typing import dataclass_transform

from ..props import updatable_props


@dataclasses.dataclass
@dataclass_transform(field_specifiers=(dataclasses.field,))
class EntityType:
    field: "updatable_props.Field" = dataclasses.field(hash=False)

    enabled: bool = dataclasses.field(default=True, kw_only=True)
    availability: "updatable_props.Field | str | None" = dataclasses.field(
        default=None, kw_only=True
    )
    translation_key: str | None = dataclasses.field(default=None, kw_only=True)
    translation_placeholders: dict[str, str] | None = dataclasses.field(
        default=None, kw_only=True
    )

    @property
    def _field(self) -> "updatable_props.Field":
        return self.field  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def availability_prop(self):
        availability: updatable_props.Field | str = self.availability  # pyright: ignore[reportAttributeAccessIssue]
        if isinstance(availability, updatable_props.Field):
            return availability.public_name
        return availability

    @property
    def key(self):
        return self._field.public_name

    def __init_subclass__(cls) -> None:
        dataclasses.dataclass(cls)


type EntityKind = type[EntityType] | EntityType


@dataclasses.dataclass
class DynamicValue[F, T]:
    field: "updatable_props.Field[F]"
    transform: Callable[[F], T] | None = None


def dynamic[F, T](
    field: "updatable_props.Field[F]", transform: Callable[[F], T] | None = None
) -> T:
    return DynamicValue(field, transform)  # pyright: ignore[reportReturnType]

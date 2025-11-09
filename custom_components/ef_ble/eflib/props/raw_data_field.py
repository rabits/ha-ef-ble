from collections.abc import Callable
from dataclasses import dataclass, fields
from functools import cached_property
from typing import TYPE_CHECKING, Any, overload

from ..model.base import RawData
from .updatable_props import Field

if TYPE_CHECKING:
    from .raw_data_props import RawDataProps


class _DataclassAttr:
    def __init__(self, message_type: type[Any], name: str):
        self.message_type = message_type
        self.attr = name

    @property
    def name(self):
        return self.attr

    def __repr__(self):
        return f"dataclass_attr({self.attr})"


@dataclass
class _DataclassAccessor[T1: RawData]:
    message_type: type[T1]

    def __getattr__(self, name: str):
        if name not in self._field_names:
            raise AttributeError(
                f"{self.message_type} does not contain field named '{name}'"
            )

        return _DataclassAttr(self.message_type, name)

    @cached_property
    def _field_names(self):
        return [field.name for field in fields(self.message_type)]


def dataclass_attr_mapper[T: RawData](dataclass: type[T]) -> type[T]:
    return _DataclassAccessor(dataclass)  # pyright: ignore[reportReturnType]


class RawDataField[T](Field[T]):
    def __init__(
        self,
        data_attr: _DataclassAttr,
        identifier: str = "",
        transform_value: Callable[[Any], T] = lambda x: x,
    ):
        self.data_attr = data_attr
        self.identifier = identifier
        self._transform_value = transform_value

    def _get_value(self, value: Any):
        if not isinstance(value, RawData):
            return value

        return getattr(value, self.data_attr.attr)

    def __set__(self, instance: "RawDataProps", value: Any):
        value = self._get_value(value)
        value = self._transform_value(value)
        super().__set__(instance, value)


@overload
def raw_field[T_ATTR](
    attr: T_ATTR,
    transform: None = None,
) -> RawDataField[T_ATTR]: ...


@overload
def raw_field[T_ATTR, T_OUT](
    attr: T_ATTR,
    transform: Callable[[T_ATTR], T_OUT],
) -> RawDataField[T_OUT]: ...


def raw_field(
    attr: Any, transform: Callable[[Any], Any] | None = None
) -> RawDataField[Any]:
    if not isinstance(attr, _DataclassAttr):
        raise TypeError(
            "Attribute has to be an instance returned from `dataclass_attr_mapper` "
            f"after attribute access, but received value of '{attr}'"
        )

    return RawDataField(
        data_attr=attr,
        transform_value=transform if transform is not None else lambda x: x,
    )

from dataclasses import dataclass
from typing import Any, ClassVar, Self, overload


class UpdatableProps:
    """
    Mixin for augmenting device classes with advanced properties

    If any property changed its value after calling `reset_updated`, attribute
    `updated` is set to True and all updated field names are added to
    `updated_fields`.

    Attributes
    ----------
    updated
        Holds True if any fields are updated after calling `reset_updated`
    """

    updated: bool = False
    _updated_fields: set[str] | None = None

    @property
    def updated_fields(self):
        """List of field names that were updated after calling `reset_updated`"""
        if self._updated_fields is None:
            self._updated_fields = set()
        return self._updated_fields

    @updated_fields.setter
    def updated_fields(self, value: list[str]):
        self._updated_fields = set(value)

    _fields: ClassVar[list["Field[Any]"]] = []

    def reset_updated(self):
        self.updated = False
        self.updated_fields.clear()

    def __str__(self) -> str:
        class_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
        field_strs = []
        for field in self._fields:
            value = getattr(self, field.public_name)
            field_strs.append(f"  {field.public_name}: {value!r}")
        fields_formatted = "\n".join(field_strs)
        return f"{class_name}:\n{fields_formatted}"


@dataclass(kw_only=True)
class Field[T]:
    """Descriptor for updating values only if they changed"""

    def __set_name__[T_PROPS: UpdatableProps](self, owner: type[T_PROPS], name: str):
        self.public_name = name
        self.private_name = (
            f"_{name}" if not hasattr(owner, f"_{name}") else f"__{name}"
        )
        owner._fields = [*owner._fields, self]

    def __set__(self, instance: UpdatableProps, value: Any):
        self._set_value(instance, value)

    def _set_value(self, instance, value):
        if not isinstance(instance, UpdatableProps):
            raise TypeError(
                f"Descriptor {self.__class__.__name__} can only be used on subclasses "
                f"of {UpdatableProps.__name__}"
            )

        if value == getattr(instance, self.public_name):
            return

        setattr(instance, self.private_name, value)
        instance.updated = True
        instance.updated_fields.add(self.public_name)

    @overload
    def __get__(self, instance: None, owner: type[UpdatableProps]) -> Self: ...

    @overload
    def __get__(
        self, instance: UpdatableProps, owner: type[UpdatableProps]
    ) -> T | None: ...

    def __get__(
        self, instance: UpdatableProps | None, owner: type[UpdatableProps]
    ) -> T | Self | None:
        if instance is None:
            return self
        return getattr(instance, self.private_name, None)

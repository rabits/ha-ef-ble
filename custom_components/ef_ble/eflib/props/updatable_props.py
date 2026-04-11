import inspect
from collections.abc import Callable, Iterator
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Self, overload

if TYPE_CHECKING:
    from ..entity import controls
    from ..entity.base import EntityKind, EntityType


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
    _fields: ClassVar[list["Field[Any]"]] = []
    _computed_fields: ClassVar[list["_ComputedField[Any]"]] = []

    @property
    def updated_fields(self):
        """List of field names that were updated after calling `reset_updated`"""
        if self._updated_fields is None:
            self._updated_fields = set()
        return self._updated_fields

    @updated_fields.setter
    def updated_fields(self, value: list[str]):
        self._updated_fields = set(value)

    def reset_updated(self):
        """Clear the updated flag and the set of changed field names"""
        self.updated = False
        self.updated_fields.clear()

    def get_value[T](self, field: "Field[T] | str") -> T:
        """Read the current value of a field by descriptor or name"""
        return getattr(
            self,
            field.public_name if isinstance(field, Field) else field,
        )

    def set_value(self, field: "Field[Any] | str", value: Any):
        """Write a value to a field by descriptor or name"""
        setattr(
            self,
            field.public_name if isinstance(field, Field) else field,
            value,
        )

    def __str__(self) -> str:
        cls = f"{self.__class__.__module__}.{self.__class__.__name__}"
        lines = [
            f"  {f.public_name}: {getattr(self, f.public_name)!r}" for f in self._fields
        ]
        return f"{cls}:\n" + "\n".join(lines)

    def _recompute(self):
        for cf in self._computed_fields:
            cf.recompute(self)

    def _notify_updated(self):
        self._recompute()
        for field_name in self.updated_fields:
            self.update_callback(field_name)  # type: ignore[attr-defined]
            self.update_state(field_name, getattr(self, field_name))  # type: ignore[attr-defined]

    def _get_entities[E: "EntityType"](
        self,
        sensor_type: type[E],
        collection_attr: str,
    ) -> list[E]:
        if getattr(self, collection_attr) is None:
            return []
        return [
            item
            for cls in inspect.getmro(type(self))
            if cls.__dict__.get(collection_attr)
            for item in cls.__dict__.get(collection_attr, [])
            if isinstance(item, sensor_type)
        ]

    @cached_property
    def _controls(self):
        return [f.sensor_type for f in self._fields if f.sensor_type is not None]

    def get_controls[E: "controls.ControlType"](
        self,
        control_type: type[E],
    ):
        """Return all registered controls matching the given type"""
        return [c for c in self._controls if isinstance(c, control_type)]


class Skip:
    """Sentinel value for skipping assignment in field's transform function"""


class Field[T]:
    """Descriptor for updating values only if they changed"""

    transform_value: Callable[[Any], T] | None = None
    sensor_type: "EntityType | None" = None

    def __set_name__[P: UpdatableProps](
        self,
        owner: type[P],
        name: str,
    ):
        self.public_name = name
        self.private_name = (
            f"_{name}" if not hasattr(owner, f"_{name}") else f"__{name}"
        )
        owner._fields = [*owner._fields, self]

    def __set__(self, instance: UpdatableProps, value: Any):
        self._set_value(instance, value)

    def _set_value(self, instance: UpdatableProps, value: Any):
        if (value := self._transform_value(value)) is Skip:
            return
        if value == getattr(instance, self.public_name):
            return
        setattr(instance, self.private_name, value)
        instance.updated = True
        instance.updated_fields.add(self.public_name)

    @property
    def _transform_value(self):
        return getattr(self, "_transform", lambda x: x)

    @_transform_value.setter
    def _transform_value(
        self,
        value: Callable[[Any], Any] | None = None,
    ):
        if value is not None:
            setattr(self, "_transform", value)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.public_name})"

    @overload
    def __get__(
        self,
        instance: None,
        owner: type[UpdatableProps],
    ) -> "Field[T]": ...

    @overload
    def __get__(
        self,
        instance: UpdatableProps,
        owner: type[UpdatableProps],
    ) -> T | None: ...

    def __get__(
        self,
        instance: UpdatableProps | None,
        owner: type[UpdatableProps],
    ) -> "T | Field | None":
        if instance is None:
            return self
        return getattr(instance, self.private_name, None)

    def sensor(
        self,
        sensor: "EntityKind",
        db_precision: int | None = None,
    ) -> Self:
        """
        Mark this field as sensor type

        Parameters
        ----------
        sensor
            Sensor type
        db_precision, optional
            Floating point precision to use for writing to db, by default None

        Returns
        -------
        Same field
        """
        if db_precision is not None:

            def _transform_precision(value: Any) -> T:
                return round(value, db_precision)

            self._transform_value = _transform_precision

        if isinstance(sensor, type):
            sensor = sensor(self)
        else:
            sensor.field = self
        self.sensor_type = sensor
        return self


class _ComputedField[T](Field[T]):
    _func: Callable[..., T]

    def __call__(self, func: Callable[..., T]) -> Self:
        self._func = func
        return self

    def __set_name__(self, owner: type[UpdatableProps], name: str):
        super().__set_name__(owner, name)
        existing = [cf for cf in owner._computed_fields if cf.public_name != name]
        owner._computed_fields = [*existing, self]

    @overload
    def __get__(
        self,
        instance: None,
        owner: type[UpdatableProps],
    ) -> "_ComputedField[T]": ...

    @overload
    def __get__(
        self,
        instance: UpdatableProps,
        owner: type[UpdatableProps],
    ) -> T: ...

    def __get__(
        self,
        instance: UpdatableProps | None,
        owner: type[UpdatableProps],
    ) -> "T | _ComputedField[T]":
        if instance is None:
            return self
        # always compute live from current state. recompute() separately diffs against a
        # cached value to track which fields changed
        return self._func(instance)

    def __set__(self, instance: UpdatableProps, value: Any):
        raise AttributeError(f"cannot set computed field '{self.public_name}' directly")

    def recompute(self, instance: UpdatableProps):
        new_val = self._func(instance)
        old_val = getattr(instance, self.private_name, None)
        if new_val == old_val:
            return
        setattr(instance, self.private_name, new_val)
        instance.updated = True
        instance.updated_fields.add(self.public_name)


def computed_field[T](func: Callable[..., T]) -> _ComputedField[T]:
    cf = _ComputedField[T]()
    cf(func)
    return cf


class FieldGroupView[T]:
    """Provides 1-based indexed access to field values on a device instance"""

    __slots__ = ("_fields", "_instance", "_start")

    def __init__(
        self,
        instance: UpdatableProps,
        fields: "list[Field[T]]",
        start: int,
    ) -> None:
        self._instance = instance
        self._fields = fields
        self._start = start

    def __getitem__(self, index: int) -> "T | None":
        field = self._fields[index - self._start]
        return field.__get__(self._instance, type(self._instance))

    def __len__(self) -> int:
        return len(self._fields)


class FieldGroup[T]:
    """
    Descriptor that creates N individually-named fields and provides indexed access

    When assigned as a class attribute with name `name`, it registers N sub-fields
    as `{name}_{start}` ... `{name}_{start + count - 1}` (or using a custom
    `name_template` / `name_prefix`).

    Class access returns the FieldGroup itself (iterable over Field descriptors).
    Instance access returns a FieldGroupView with 1-based __getitem__.

    Parameters
    ----------
    factory
        Callable receiving the 1-based index and returning a Field instance
    count
        Number of fields to create
    start
        Index of the first field (default 1)
    name_template
        Explicit naming pattern with {n} placeholder, e.g. "ch{n}_status"
    name_prefix
        Prefix with {n} placeholder — the template is derived automatically
        from the class attribute name (used by `pb_group`)
    """

    def __init__(
        self,
        factory: "Callable[[int], Field[T]]",
        count: int,
        *,
        start: int = 1,
        name_template: str | None = None,
        name_prefix: str | None = None,
    ) -> None:
        self._count = count
        self._start = start
        self._name_template = name_template
        self._name_prefix = name_prefix
        self._fields: list[Field[T]] = [factory(i) for i in range(start, start + count)]
        self._name: str = ""

    @property
    def start(self) -> int:
        return self._start

    def _resolve_template(self, name: str) -> str | None:
        if self._name_template is not None:
            return self._name_template
        if self._name_prefix is not None:
            base = self._name_prefix.replace("{n}", "")
            return self._name_prefix + name[len(base) :]
        return None

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name
        template = self._resolve_template(name)
        for i, field in enumerate(self._fields, start=self._start):
            field_name = template.format(n=i) if template else f"{name}_{i}"
            field.__set_name__(owner, field_name)
            setattr(owner, field_name, field)

    @overload
    def __get__(
        self,
        instance: None,
        owner: type,
    ) -> "FieldGroup[T]": ...

    @overload
    def __get__(
        self,
        instance: UpdatableProps,
        owner: type,
    ) -> "FieldGroupView[T]": ...

    def __get__(
        self,
        instance: UpdatableProps | None,
        owner: type,
    ) -> "FieldGroup[T] | FieldGroupView[T]":
        if instance is None:
            return self
        return FieldGroupView(instance, self._fields, self._start)

    def __iter__(self) -> "Iterator[Field[T]]":
        return iter(self._fields)

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, index: int) -> "Field[T]":
        return self._fields[index - self._start]


def field_group[T](
    factory: "Callable[[int], Field[T]]",
    count: int,
    *,
    start: int = 1,
    name_template: str | None = None,
) -> "FieldGroup[T]":
    """
    Create a group of count related fields named `{attr}_{start}` ... `{attr}_{N}`

    When assigned to a class attribute with name `name`, the individual fields are
    registered as `{name}_{start}` through `{name}_{start + count - 1}`.

    Parameters
    ----------
    factory
        Callable receiving the 1-based index and returning a Field instance
    count
        Number of fields to create
    start
        Index of the first field (default 1)
    name_template
        Explicit naming pattern with {n} placeholder, e.g. "ch{n}_status"
    """
    return FieldGroup(
        factory,
        count,
        start=start,
        name_template=name_template,
    )

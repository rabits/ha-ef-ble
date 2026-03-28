import dataclasses
import inspect
from collections.abc import Awaitable, Callable, Iterable
from typing import TYPE_CHECKING, Any, cast, get_type_hints

from ..props.enums import IntFieldValue
from . import DynamicValue, EntityType, units

if TYPE_CHECKING:
    from ..devicebase import DeviceBase
    from ..props import updatable_props


def _resolve(
    value: "float | DynamicValue | None", device: "DeviceBase"
) -> float | None:
    """Resolve a plain float or a DynamicValue against the device."""
    if isinstance(value, DynamicValue):
        raw = getattr(device, value.field.public_name, None)  # pyright: ignore[reportAttributeAccessIssue]
        if raw is None:
            return None
        return value.transform(raw) if value.transform is not None else float(raw)
    return value


class ControlType(EntityType):
    pass


@dataclasses.dataclass
class toggle(ControlType):
    type SwitchFunc[D: "DeviceBase"] = Callable[[D, bool], Awaitable[None]]

    enable_func: SwitchFunc = dataclasses.field(
        default=cast("SwitchFunc", None),
        repr=False,
        init=False,
    )

    def __call__[D: "DeviceBase"](
        self,
        func: Callable[[D, bool], Awaitable[None]],
    ):
        _check_value_param(func, bool, type(self).__name__)
        self.enable_func = func
        self._field.sensor(self)
        return func


class outlet(toggle):
    pass


class switch(toggle):
    pass


class NumberType(ControlType):
    type ValueFunc[D: "DeviceBase", N] = Callable[[D, N], Awaitable[bool]]

    set_value_func: ValueFunc = dataclasses.field(
        default=cast("Any", None),
        repr=False,
        init=False,
    )
    max: float | None = None
    min: float = 0
    step: float = 1.0

    def __call__[F: Callable[[Any, float], Awaitable[bool]]](
        self,
        func: F,
    ) -> F:
        _check_value_param(func, float, type(self).__name__)

        control = self

        async def _check_limits(device: "DeviceBase", value: float) -> bool:
            if (low := _resolve(control.min, device)) is not None:
                value = max(low, value)
            if (high := _resolve(control.max, device)) is not None:
                value = min(high, value)
            return await func(device, value)

        self.set_value_func = _check_limits

        self._field.sensor(self)
        return func


class power(NumberType):
    unit: units.Power = units.Power.WATT


class battery(NumberType):
    pass


class current(NumberType):
    unit: units.Current = units.Current.AMPERE


class voltage(NumberType):
    unit: units.Voltage = units.Voltage.VOLT


class temperature(NumberType):
    unit: units.Temperature = units.Temperature.C


class weight(NumberType):
    pass


class select[E: IntFieldValue](ControlType):
    type SetFunc = Callable[[DeviceBase, E], Awaitable[None]]

    options: type[E] | list[str]
    set_value_func: SetFunc = dataclasses.field(
        repr=False,
        init=False,
    )

    def __post_init__(self) -> None:
        if isinstance(self.options, list):
            self._value_type: type[E] | None = None
        else:
            self._value_type = self.options
            self.options = self.options.options(include_unknown=False)

    @property
    def options_str(self) -> list[str]:
        return (
            self.options
            if isinstance(self.options, list)
            else self.options.options(include_unknown=False)
        )

    def __call__[D: "DeviceBase"](
        self,
        func: Callable[[D, E], Awaitable[None]],
    ):
        if self._value_type is not None:
            _check_value_param(func, self._value_type, type(self).__name__)

        value_type = self._value_type

        async def _func(device: D, value: E | str) -> None:
            if isinstance(value, str) and value_type is not None:
                value = value_type[value.upper()]

            await func(device, value)  # pyright: ignore[reportArgumentType]

        self.set_value_func = _func  # pyright: ignore[reportAttributeAccessIssue]
        self._field.sensor(self)
        return _func


def for_each(
    fields: "Iterable[updatable_props.Field]",
    *,
    control: "type[toggle]",
    availability: "Iterable[updatable_props.Field | None] | None" = None,
    translation_key: str | None = None,
    translation_placeholders: "Callable[[int], dict[str, str]] | None" = None,
) -> "Callable[[Callable], Callable]":
    """
    Decorator that registers a toggle control for each field in the list

    The decorated function must accept (self, index: int, enabled: bool) where
    index is 1-based (i.e. 1 for the first field, 2 for the second, etc.).
    """

    def decorator(func: "Callable") -> "Callable":
        avail_iter = iter(availability) if availability is not None else None
        for i, field in enumerate(fields):
            circuit_id = i + 1
            avail = next(avail_iter) if avail_iter is not None else None
            placeholders = (
                translation_placeholders(circuit_id)
                if translation_placeholders is not None
                else None
            )
            ctrl = control(
                field,
                availability=avail,
                translation_key=translation_key,
                translation_placeholders=placeholders,
            )

            async def _enable(
                device: "DeviceBase",
                enabled: bool,
                _cid: int = circuit_id,
            ) -> None:
                await func(device, _cid, enabled)

            ctrl.enable_func = _enable
            field.sensor(ctrl)

        return func

    return decorator


def _check_value_param(func: Any, expected: type, decorator_name: str) -> None:
    hints = get_type_hints(func)
    params = list(inspect.signature(func).parameters.values())
    if len(params) < 2:
        raise TypeError(
            f"@{decorator_name}: decorated function must accept "
            f"(self, value: {expected.__name__})"
        )
    value_param = params[1]
    value_type = hints.get(value_param.name)
    if value_type is not None and value_type is not expected:
        raise TypeError(
            f"@{decorator_name}: parameter '{value_param.name}' must be "
            f"{expected.__name__}, got {value_type}"
        )

import dataclasses
import enum
import inspect
from collections.abc import Awaitable, Callable, Iterable
from typing import TYPE_CHECKING, Any, cast, get_type_hints

from ..props.enums import IntFieldValue
from . import DynamicValue, EntityType, units

if TYPE_CHECKING:
    from ..devicebase import DeviceBase
    from ..props import updatable_props


class HvacMode(enum.StrEnum):
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    HEAT_COOL = "heat_cool"
    AUTO = "auto"
    DRY = "dry"
    FAN_ONLY = "fan_only"


def _resolve(value: float | DynamicValue | None, device: "DeviceBase") -> float | None:
    if isinstance(value, DynamicValue):
        raw = getattr(device, value.field.public_name, None)  # pyright: ignore[reportAttributeAccessIssue]
        if raw is None:
            return None
        return value.transform(raw) if value.transform is not None else float(raw)
    return value


class ControlType(EntityType):
    pass


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
    type ValueFunc[D: "DeviceBase", float] = Callable[[D, float], Awaitable[bool]]

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
        return cast("F", _check_limits)


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
    control: type[toggle],
    availability: "Iterable[updatable_props.Field | None] | None" = None,
    translation_key: str | None = None,
    translation_placeholders: Callable[[int], dict[str, str]] | None = None,
) -> Callable[[Callable], Callable]:
    """
    Decorate a function to register a toggle control for each field in the list

    The decorated function must accept (self, index: int, enabled: bool) where
    index is 1-based (i.e. 1 for the first field, 2 for the second, etc.).
    """

    def decorator(func: Callable) -> Callable:
        avail_iter = iter(availability) if availability is not None else None
        for i, field in enumerate(fields):
            idx = i + 1
            avail = next(avail_iter) if avail_iter is not None else None
            placeholders = (
                translation_placeholders(idx)
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
                _id: int = idx,
            ) -> None:
                await func(device, _id, enabled)

            ctrl.enable_func = _enable
            field.sensor(ctrl)

        return func

    return decorator


type _PowerSetter = Callable[[Any, bool], Awaitable[None]]
type _ModeSetter = Callable[[Any, Any], Awaitable[None]]
type _TargetTempSetter = Callable[[Any, float], Awaitable[None]]
type _TargetTempRangeSetter = Callable[[Any, float, float], Awaitable[None]]
type _HumiditySetter = Callable[[Any, int], Awaitable[None]]
type _FanSpeedSetter = Callable[[Any, Any], Awaitable[None]]
type _Decorator[F] = Callable[[F], F]


class climate(ControlType):
    """
    Control type for composite climate entities

    Bundles power, operating mode, target temperature, fan speed, and current
    temperature into a single control that the climate platform discovers via
    get_controls.
    """

    hvac_modes: dict[str, Any] = dataclasses.field(default_factory=dict)
    fan_modes: dict[str, Any] = dataclasses.field(default_factory=dict)

    # shared, read-only field (no associated setter decorator). Typed as Any because
    # `updatable_props.Field` is a data descriptor - annotating with it makes type
    # checkers route plain assignments through Field.__set__, which only accepts
    # `UpdatableProps` instances (devices), not this control dataclass
    current_temperature_field: Any = None

    temperature_unit: str = "°C"

    target_temperature_step: float = dataclasses.field(
        default=1.0, repr=False, init=False
    )
    min_temp: float | None = dataclasses.field(default=None, repr=False, init=False)
    max_temp: float | None = dataclasses.field(default=None, repr=False, init=False)
    target_temperature_range_step: float = dataclasses.field(
        default=1.0, repr=False, init=False
    )
    min_range_temp: float | None = dataclasses.field(
        default=None, repr=False, init=False
    )
    max_range_temp: float | None = dataclasses.field(
        default=None, repr=False, init=False
    )
    min_humidity: int | None = dataclasses.field(default=None, repr=False, init=False)
    max_humidity: int | None = dataclasses.field(default=None, repr=False, init=False)

    power_field: Any = dataclasses.field(default=None, repr=False, init=False)
    target_temperature_field: Any = dataclasses.field(
        default=None, repr=False, init=False
    )
    target_temperature_low_field: Any = dataclasses.field(
        default=None, repr=False, init=False
    )
    target_temperature_high_field: Any = dataclasses.field(
        default=None, repr=False, init=False
    )
    target_humidity_field: Any = dataclasses.field(default=None, repr=False, init=False)
    fan_speed_field: Any = dataclasses.field(default=None, repr=False, init=False)

    set_power: "_PowerSetter | None" = dataclasses.field(
        default=None, repr=False, init=False
    )
    set_operating_mode: "_ModeSetter | None" = dataclasses.field(
        default=None, repr=False, init=False
    )
    set_target_temperature: "_TargetTempSetter | None" = dataclasses.field(
        default=None, repr=False, init=False
    )
    set_target_temperature_range: "_TargetTempRangeSetter | None" = dataclasses.field(
        default=None, repr=False, init=False
    )
    set_target_humidity: "_HumiditySetter | None" = dataclasses.field(
        default=None, repr=False, init=False
    )
    set_fan_speed: "_FanSpeedSetter | None" = dataclasses.field(
        default=None, repr=False, init=False
    )

    target_temperature_hvac_modes: frozenset[str] | None = dataclasses.field(
        default=None, repr=False, init=False
    )
    target_temperature_range_hvac_modes: frozenset[str] | None = dataclasses.field(
        default=None, repr=False, init=False
    )
    target_humidity_hvac_modes: frozenset[str] | None = dataclasses.field(
        default=None, repr=False, init=False
    )
    fan_speed_hvac_modes: frozenset[str] | None = dataclasses.field(
        default=None, repr=False, init=False
    )

    def __post_init__(self):
        """Register this climate control on its field."""
        self._field.sensor(self)

    def __call__(self, func: Any) -> Any:
        return func

    def power(self, field: Any = None, /) -> _Decorator[_PowerSetter]:
        def bind(f: _PowerSetter) -> _PowerSetter:
            self.set_power = _virtual_dispatch(f, notify_fields=[field])
            if field is not None:
                self.power_field = field
            return f

        return bind

    def mode(self) -> _Decorator[_ModeSetter]:
        base_field = self._field

        def bind(f: _ModeSetter) -> _ModeSetter:
            self.set_operating_mode = _virtual_dispatch(f, notify_fields=[base_field])
            return f

        return bind

    def target_temp(
        self,
        field: Any = None,
        /,
        *,
        modes: Iterable[str] | None = None,
        step: float | None = None,
        min: float | None = None,
        max: float | None = None,
    ) -> _Decorator[_TargetTempSetter]:
        def bind(f: _TargetTempSetter) -> _TargetTempSetter:
            self.set_target_temperature = _virtual_dispatch(f, notify_fields=[field])
            if field is not None:
                self.target_temperature_field = field
            if modes is not None:
                self.target_temperature_hvac_modes = frozenset(modes)
            if step is not None:
                self.target_temperature_step = step
            if min is not None:
                self.min_temp = min
            if max is not None:
                self.max_temp = max
            return f

        return bind

    def target_temp_range(
        self,
        low: Any = None,
        high: Any = None,
        /,
        *,
        modes: Iterable[str] | None = None,
        step: float | None = None,
        min: float | None = None,
        max: float | None = None,
    ) -> _Decorator[_TargetTempRangeSetter]:
        def bind(f: _TargetTempRangeSetter) -> _TargetTempRangeSetter:
            self.set_target_temperature_range = _virtual_dispatch(
                f, notify_fields=[low, high]
            )
            if low is not None:
                self.target_temperature_low_field = low
            if high is not None:
                self.target_temperature_high_field = high
            if modes is not None:
                self.target_temperature_range_hvac_modes = frozenset(modes)
            if step is not None:
                self.target_temperature_range_step = step
            if min is not None:
                self.min_range_temp = min
            if max is not None:
                self.max_range_temp = max
            return f

        return bind

    def humidity(
        self,
        field: Any = None,
        /,
        *,
        modes: Iterable[str] | None = None,
        min: int | None = None,
        max: int | None = None,
    ) -> _Decorator[_HumiditySetter]:
        def bind(f: _HumiditySetter) -> _HumiditySetter:
            self.set_target_humidity = _virtual_dispatch(f, notify_fields=[field])
            if field is not None:
                self.target_humidity_field = field
            if modes is not None:
                self.target_humidity_hvac_modes = frozenset(modes)
            if min is not None:
                self.min_humidity = min
            if max is not None:
                self.max_humidity = max
            return f

        return bind

    def fan(
        self,
        field: Any = None,
        /,
        *,
        modes: Iterable[str] | None = None,
    ) -> _Decorator[_FanSpeedSetter]:
        def bind(f: _FanSpeedSetter) -> _FanSpeedSetter:
            self.set_fan_speed = _virtual_dispatch(f, notify_fields=[field])
            if field is not None:
                self.fan_speed_field = field
            if modes is not None:
                self.fan_speed_hvac_modes = frozenset(modes)
            return f

        return bind


def _virtual_dispatch(func: Any, *, notify_fields: Iterable[Any] | None = None) -> Any:
    name = func.__name__
    fields = tuple(notify_fields) if notify_fields is not None else ()

    async def _dispatch(device: "DeviceBase", *args: Any, **kwargs: Any) -> Any:
        result = await getattr(device, name)(*args, **kwargs)
        for field, value in zip(fields, args, strict=False):
            if field is not None:
                device.notify_field(field, value)
        return result

    return _dispatch


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

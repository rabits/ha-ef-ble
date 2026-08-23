"""Advanced per-device options shared by several device families"""

from .devicebase import DeviceBase, DeviceOption
from .props.updatable_props import UpdatableProps, _ComputedField

UNLOCK_AC_CHARGING_MINIMUM = DeviceOption("unlock_ac_charging_minimum", default=False)
UNLOCK_DC_CHARGING_MINIMUM = DeviceOption("unlock_dc_charging_minimum", default=False)


class _OptionField[T](_ComputedField[T]):
    def __init__(self, option: DeviceOption[bool], enabled: T, disabled: T) -> None:
        self._option = option

        def value(device: DeviceBase) -> T:
            return enabled if device.advanced_option(option) else disabled

        self(value)

    def __set_name__(self, owner: type[UpdatableProps], name: str):
        super().__set_name__(owner, name)
        if not issubclass(owner, DeviceBase):
            raise TypeError(
                f"{owner.__name__}.{name}: option_field reads an option off the "
                f"device, so it belongs on a DeviceBase subclass"
            )
        owner.ADVANCED_OPTIONS = tuple(
            dict.fromkeys([*owner.ADVANCED_OPTIONS, self._option])
        )


def option_field[T](
    option: DeviceOption[bool], *, enabled: T, disabled: T
) -> _OptionField[T]:
    """
    Field reading `enabled` or `disabled` depending on a boolean device option

    Declaring it also registers `option` in the owner's `ADVANCED_OPTIONS`, so whatever
    surfaces those options picks it up without a second declaration. Override the field
    in a subclass to change the values for that model: `dynamic()` resolves fields by
    name, so the subclass's version is what a control's limits read.
    """
    return _OptionField(option, enabled, disabled)

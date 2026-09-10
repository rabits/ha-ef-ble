from ..device_options import UNLOCK_AC_CHARGING_MINIMUM, option_field
from ..props import computed_field
from . import delta3


class Device(delta3.Device):
    """Delta 3 Max"""

    SN_PREFIX = (b"D3N1",)

    ac_charging_speed_min = option_field(
        UNLOCK_AC_CHARGING_MINIMUM, enabled=1, disabled=200
    )

    @computed_field
    def ac_charging_power_max(self) -> int:
        return 1800

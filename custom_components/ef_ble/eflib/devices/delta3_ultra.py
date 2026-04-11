from ..props import computed_field
from . import delta3


class Device(delta3.Device):
    """Delta 3 Ultra"""

    SN_PREFIX = (b"D751",)

    @computed_field
    def max_ac_charging_power(self) -> int:
        return 1800

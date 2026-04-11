from ..props import computed_field
from . import delta2


class Device(delta2.Device):
    """Delta 3 1500"""

    SN_PREFIX = (b"D361",)
    NAME_PREFIX = "EF-D3"

    @computed_field
    def max_ac_charging_power(self) -> int:
        return 1500

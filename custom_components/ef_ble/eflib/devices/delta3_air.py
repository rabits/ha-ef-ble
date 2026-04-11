from ..props import computed_field
from ._delta3_base import Delta3Base


class Device(Delta3Base):
    """Delta 3 Air"""

    SN_PREFIX = (b"PR11", b"PR12", b"PR21")
    NAME_PREFIX = "EF-PR"

    @computed_field
    def max_ac_charging_power(self) -> int:
        return 1000 if self._sn[:4] == "PR21" else 500

    @property
    def device(self):
        model = "Air"
        match self._sn[:4]:
            case "PR11":
                model = "1000 Air"
            case "PR12":
                model = "1000 Air (10ms UPS)"
            case "PR21":
                model = "2000 Air"
        return f"Delta 3 {model}"

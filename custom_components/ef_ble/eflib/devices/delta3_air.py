from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ._delta3_base import Delta3Base


class Device(Delta3Base):
    """Delta 3 Air"""

    SN_PREFIX = (b"PR11", b"PR12", b"PR21")
    NAME_PREFIX = "EF-PR"

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self.max_ac_charging_power = 500

    @property
    def device(self):
        model = "Air"
        match self._sn[:4]:
            case b"PR11":
                model = "1000 Air"
            case b"PR12":
                model = "1000 Air (10ms UPS)"
            case b"PR21":
                model = "Delta 3 2000 Air"
        return f"Delta 3 {model}"

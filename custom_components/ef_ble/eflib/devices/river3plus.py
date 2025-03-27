from enum import IntEnum

from custom_components.ef_ble.eflib.devices import river3

from ..pb import pr705_pb2
from ..props import pb_field


class LedMode(IntEnum):
    OFF = 0
    DIM = 1
    BRIGHT = 2
    SOS = 3


class Device(river3.Device):
    """River 3 Plus"""

    SN_PREFIX = (b"R631", b"R634")

    battery_level_main = pb_field(river3.pb.bms_batt_soc)

    led_mode = pb_field(river3.pb.led_mode, lambda num: LedMode(num))

    async def set_led_mode(self, state: LedMode):
        await self._send_config_packet(pr705_pb2.ConfigWrite(cfg_led_mode=state.value))

    @property
    def device(self):
        return "River 3 Plus"

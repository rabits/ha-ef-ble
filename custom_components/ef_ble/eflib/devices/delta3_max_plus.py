from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..pb import pd335_sys_pb2
from ..props import pb_field
from . import delta3_plus
from ._delta3_base import flow_is_on

pb = delta3_plus.pb


class Device(delta3_plus.Device):
    """Delta 3 Max Plus"""

    SN_PREFIX = (b"D3M1",)

    ac_ports_2 = pb_field(pb.flow_info_ac2_out, flow_is_on)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self.max_ac_charging_power = 2400

    async def enable_ac_ports_2(self, enabled: bool):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_ac2_out_open=enabled)
        )

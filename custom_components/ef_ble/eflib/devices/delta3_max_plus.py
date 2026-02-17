from collections.abc import Sequence

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..pb import pd335_sys_pb2
from ..props import pb_field, repeated_pb_field_type
from . import delta3_plus
from ._delta3_base import flow_is_on

pb = delta3_plus.pb


class _ACPortPower(repeated_pb_field_type(pb.pow_get_ac_out_list.pow_get_ac_out_item)):
    index: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.index], 2) if value else None


class Device(delta3_plus.Device):
    """Delta 3 Max Plus"""

    SN_PREFIX = (b"D3M1",)

    ac_ports_2 = pb_field(pb.flow_info_ac2_out, flow_is_on)

    ac_power_1 = _ACPortPower(0)
    ac_power_2 = _ACPortPower(3)

    usbc3_output_power = pb_field(pb.pow_get_typec3)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self.max_ac_charging_power = 2400

    async def enable_ac_ports_2(self, enabled: bool):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_ac2_out_open=enabled)
        )

from ..entity import controls
from ..pb import bk_series_pb2
from ..props import pb_field
from ..props.transforms import pround
from . import stream_ac

pb = stream_ac.pb


class Device(stream_ac.Device):
    """STREAM Max"""

    SN_PREFIX = (b"BK41",)

    ac_power_1 = pb_field(pb.pow_get_schuko1)
    ac_1 = pb_field(pb.relay2_onoff)

    pv_power_1 = pb_field(pb.pow_get_pv, pround(2))
    pv_power_2 = pb_field(pb.pow_get_pv4, pround(2))

    pv_power_sum = pb_field(pb.pow_get_pv_sum, pround(2))

    load_from_pv = pb_field(pb.pow_get_sys_load_from_pv, pround(2))

    @controls.outlet(ac_1)
    async def enable_ac_1(self, enable: bool):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_relay2_onoff=enable)
        )

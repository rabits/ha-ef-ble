from ..entity import controls
from ..pb import bk_series_pb2
from ..props import pb_field
from ..props.transforms import pround
from . import stream_ac, stream_max

pb = stream_ac.pb


class Device(stream_max.Device):
    """STREAM Pro"""

    SN_PREFIX = (b"BK12",)

    ac_power_2 = pb_field(pb.pow_get_schuko2, pround(2))
    ac_2 = pb_field(pb.relay3_onoff)

    pv_power_3 = pb_field(pb.pow_get_pv3, pround(2))

    @controls.outlet(ac_2)
    async def enable_ac_2(self, enable: bool):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_relay3_onoff=enable)
        )

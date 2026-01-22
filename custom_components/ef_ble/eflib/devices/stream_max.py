from ..props import pb_field
from . import stream_ac

pb = stream_ac.pb


class Device(stream_ac.Device):
    """STREAM Max"""

    SN_PREFIX = (b"BK41",)

    ac_power_1 = pb_field(pb.pow_get_schuko1)
    ac_1 = pb_field(pb.relay2_onoff)

    pv_power_1 = pb_field(pb.pow_get_pv, lambda v: round(v, 2))
    pv_power_2 = pb_field(pb.pow_get_pv4, lambda v: round(v, 2))

    load_from_pv = pb_field(pb.pow_get_sys_load_from_pv, lambda v: round(v, 2))

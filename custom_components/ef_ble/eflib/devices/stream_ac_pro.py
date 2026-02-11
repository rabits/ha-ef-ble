from ..devices import stream_ac
from ..props import ProtobufProps, pb_field

pb = stream_ac.pb


class Device(stream_ac.Device, ProtobufProps):
    """STREAM AC PRO"""

    SN_PREFIX = (b"BK31",)

    ac_power_1 = pb_field(pb.pow_get_schuko1)
    ac_power_2 = pb_field(pb.pow_get_schuko2)

    ac_1 = pb_field(pb.relay2_onoff)
    ac_2 = pb_field(pb.relay3_onoff)

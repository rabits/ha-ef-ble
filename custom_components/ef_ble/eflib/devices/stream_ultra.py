from ..props import pb_field
from . import stream_ac, stream_pro

pb = stream_ac.pb


class Device(stream_pro.Device):
    """STREAM Ultra"""

    SN_PREFIX = (b"BK11", b"ES11", b"BK61")

    pv_power_4 = pb_field(pb.pow_get_pv2, lambda v: round(v, 2))

    @property
    def device(self):
        model = ""
        match self._sn[:4]:
            case "BK61":
                model = "X"
        return f"STREAM Ultra {model}".strip()

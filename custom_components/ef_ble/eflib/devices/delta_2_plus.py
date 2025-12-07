from ..props.raw_data_props import RawDataProps
from . import delta2


class Device(delta2.Device, RawDataProps):
    """Delta 3 1500"""

    SN_PREFIX = (b"D361",)
    NAME_PREFIX = "EF-D3"

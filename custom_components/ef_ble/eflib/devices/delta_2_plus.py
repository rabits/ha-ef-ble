from ..devicebase import DeviceBase
from ..props.raw_data_props import RawDataProps


class Device(DeviceBase, RawDataProps):
    """Delta 3 1500"""

    SN_PREFIX = (b"D361",)
    NAME_PREFIX = "EF-D3"

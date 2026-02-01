from . import river2


class Device(river2.Device):
    """EcoFlow River 2 Pro."""

    NAME_PREFIX = "EF-R62"
    SN_PREFIX = (b"R621", "R623")

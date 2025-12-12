from . import delta2


class Device(delta2.Device):
    """Delta 2 Max"""

    SN_PREFIX = (b"R351", b"R354")
    NAME_PREFIX = "EF-R35"

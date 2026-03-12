from . import river2

pb_pd = river2.pb_pd
pb_mppt = river2.pb_mppt


class Device(river2.Device):
    """River 2 Pro"""

    SN_PREFIX = (b"R621", b"R623")

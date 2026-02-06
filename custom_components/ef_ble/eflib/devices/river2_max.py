from . import river2

pb_inv = river2.pb_inv
pb_pd = river2.pb_pd
pb_mppt = river2.pb_mppt


class Device(river2.Device):
    """River 2 Max"""

    SN_PREFIX = (b"R611", "R613")

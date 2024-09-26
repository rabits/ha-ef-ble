import logging

from ..devicebase import DeviceBase
from ..packet import Packet

_LOGGER = logging.getLogger(__name__)

class Device(DeviceBase):
    '''Delta Pro Ultra'''
    SN_PREFIX = b'Y711'

    @staticmethod
    def check(sn):
        return sn.startswith(Device.SN_PREFIX)

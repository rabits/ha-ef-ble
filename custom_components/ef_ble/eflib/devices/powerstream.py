from ..devicebase import DeviceBase
from ..packet import Packet
from ..ps_connection import PowerStreamConnection


class Device(DeviceBase):
    """PowerStream 600W"""

    SN_PREFIX = (b"HW51",)
    NAME_PREFIX = "EF-HW"

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    def _create_connection(self, **kwargs):
        return PowerStreamConnection(**kwargs)

    async def data_parse(self, packet: Packet) -> bool:
        return False

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..devicebase import DeviceBase
from ..packet import Packet


class Device(DeviceBase):
    """Delta 2"""

    SN_PREFIX = b"R331"
    NAME_PREFIX = "EF-R33"

    @classmethod
    def check(cls, sn):
        return sn.startswith(cls.SN_PREFIX)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)

    async def packet_parse(self, data: bytes) -> Packet:
        # Delta 2 uses V2 protocol with XOR encoding based on sequence number
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet) -> bool:
        """Processing the incoming notifications from the device"""
        # TODO: Delta 2 protobuf messages need to be identified
        # For now, just log unknown packets
        self._logger.debug(
            "%s: %s: Unknown packet: src=0x%02X, cmdSet=0x%02X, cmdId=0x%02X, payload=%s",
            self.address,
            self.name,
            packet.src,
            packet.cmdSet,
            packet.cmdId,
            packet.payloadHex,
        )
        return False

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..devicebase import DeviceBase
from ..model import (
    AllKitDetailData,
    BasePdHeart,
)
from ..packet import Packet
from ..props.raw_data_field import dataclass_attr_mapper
from ..props.raw_data_props import RawDataProps

pb_pd = dataclass_attr_mapper(BasePdHeart)


class Device(DeviceBase, RawDataProps):
    SN_PREFIX = (
        b"DCA",
        b"DCK",
        b"DCE",
        b"DCC",
        b"DCU",
        b"DCT",
        b"DCG",
        b"DCS",
        b"DCF",
        b"Z1",
        b"R511",
    )
    NAME_PREFIX = "EF-DC"

    @property
    def packet_version(self) -> int:
        return 0x02

    @property
    def auth_header_dst(self) -> int:
        return 0x32

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)

        self.index = 0
        self.add_timer_task(self.request_heartbeat, 0.3)
        self._dormant = True

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return (
            sn[:4] in cls.SN_PREFIX
            or sn[:3] in cls.SN_PREFIX
            or sn[:2] in cls.SN_PREFIX
        )

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet) -> bool:
        self.reset_updated()

        match packet.src, packet.cmdSet, packet.cmdId:
            case 0x03, 0x03, 0x0E:
                self.initialized = True
                self.update_from_bytes(AllKitDetailData, packet.payload)
            case 0x03, 0x32, 0x05:
                if self._dormant:
                    # dormancy status
                    await self._conn.sendPacket(
                        Packet(
                            src=0x21,
                            dst=0x32,
                            cmd_set=0x33,
                            cmd_id=0x01,
                            payload=b"\x01",
                            version=self.packet_version,
                        )
                    )
                    self._dormant = False

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return False

    async def send_wake_up(self):
        await self._conn.sendPacket(
            Packet(
                src=0x21,
                dst=0x03,
                cmd_set=0x32,
                cmd_id=0x05,
                payload=b"\x01",
                version=self.packet_version,
            )
        )

    async def request_heartbeat(self):
        cmd_map = {
            0: (0x21, 0x02, 0x20, 0x02),
            1: (0x21, 0x05, 0x20, 0x02),
            2: (0x21, 0x04, 0x20, 0x02),
            3: (0x21, 0x03, 0x20, 0x02),
            4: (0x21, 0x03, 0x20, 0x32),
            5: (0x21, 0x05, 0x20, 0x48),
        }

        src, dst, cmd_set, cmd_id = cmd_map[self.index]
        self.index = (self.index + 1) % 6

        if not self._dormant:
            await self._conn.sendPacket(
                Packet(
                    src=src,
                    dst=dst,
                    cmd_set=cmd_set,
                    cmd_id=cmd_id,
                    payload=b"\x00",
                    version=self.packet_version,
                )
            )

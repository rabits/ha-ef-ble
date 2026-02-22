from asyncio import Lock

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..devicebase import DeviceBase
from ..model import (
    AllKitDetailData,
    DirectBmsMDeltaHeartbeatPack,
    DirectEmsDeltaHeartbeatPack,
    DirectInvDeltaHeartbeatPack,
    DirectMpptHeartbeatPack,
    DirectPdDeltaProHeartbeatPack,
)
from ..packet import Packet
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

rd_pd = dataclass_attr_mapper(DirectPdDeltaProHeartbeatPack)
rd_bms = dataclass_attr_mapper(DirectBmsMDeltaHeartbeatPack)
rd_ems = dataclass_attr_mapper(DirectEmsDeltaHeartbeatPack)
rd_inv = dataclass_attr_mapper(DirectInvDeltaHeartbeatPack)
rd_mppt = dataclass_attr_mapper(DirectMpptHeartbeatPack)


class Device(DeviceBase, RawDataProps):
    """Delta Pro"""

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

    battery_level = raw_field(rd_ems.f32_lcd_show_soc, lambda x: round(x, 2))

    ac_output_power = raw_field(rd_inv.output_watts)
    ac_input_power = raw_field(rd_inv.input_watts)
    # ac_charging_speed = raw_field(rd_inv.cfg_slow_chg_watts)
    ac_input_voltage = raw_field(rd_inv.ac_in_vol, lambda x: round(x / 1000, 2))
    ac_input_current = raw_field(rd_inv.ac_in_amp, lambda x: round(x / 1000, 2))

    input_power = raw_field(rd_pd.watts_in_sum)
    output_power = raw_field(rd_pd.watts_out_sum)
    dc_output_power = raw_field(rd_pd.car_watts)

    usbc_output_power = raw_field(rd_pd.typec1_watts)
    usbc2_output_power = raw_field(rd_pd.typec2_watts)
    usba_output_power = raw_field(rd_pd.usb1_watts)
    usba2_output_power = raw_field(rd_pd.usb2_watts)
    qc_usb1_output_power = raw_field(rd_pd.qc_usb1_watts)
    qc_usb2_output_power = raw_field(rd_pd.qc_usb2_watts)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._lock = Lock()

        self.index = 0
        self._dormant = True
        self._wake_up_sent = False
        self._initialized = False
        self._kit_data: AllKitDetailData | None = None

        self.add_timer_task(self.request_heartbeat, 0.35)

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
                async with self._lock:
                    self._initialized = True
                self.update_from_bytes(AllKitDetailData, packet.payload)

            case 0x03, 0x32, 0x05:
                async with self._lock:
                    dormant = self._dormant

                if dormant:
                    # dormancy status
                    await self._conn.sendPacket(
                        Packet(
                            src=0x21,
                            dst=0x32,
                            cmd_set=0x33,
                            cmd_id=0x01,
                            payload=b"\x01",
                            version=self.packet_version,
                        ),
                        wait_for_response=False,
                    )

                    async with self._lock:
                        self._dormant = False
            case 0x02, 0x20, 0x02:
                self.update_from_bytes(DirectPdDeltaProHeartbeatPack, packet.payload)
            case 0x03, 0x20, 0x32:
                self.update_from_bytes(DirectBmsMDeltaHeartbeatPack, packet.payload)
            case 0x03, 0x20, 0x02:
                self.update_from_bytes(DirectEmsDeltaHeartbeatPack, packet.payload)
            case 0x04, 0x20, 0x02:
                self.update_from_bytes(DirectInvDeltaHeartbeatPack, packet.payload)
            case 0x05, 0x20, 0x02:
                self.update_from_bytes(DirectMpptHeartbeatPack, packet.payload)
            case _:
                return False

        async with self._lock:
            wake_up = False
            if self._initialized and not self._wake_up_sent:
                wake_up = True

        if wake_up:
            await self.send_wake_up()

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return True

    async def send_wake_up(self):
        async with self._lock:
            self._wake_up_sent = True

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
        async with self._lock:
            if self._dormant:
                return

        cmd_map = {
            0: (0x21, 0x02, 0x20, 0x02),
            1: (0x21, 0x05, 0x20, 0x02),
            2: (0x21, 0x04, 0x20, 0x02),
            3: (0x21, 0x03, 0x20, 0x02),
            4: (0x21, 0x03, 0x20, 0x32),
            # 5: (0x21, 0x05, 0x20, 0x48),
        }

        src, dst, cmd_set, cmd_id = cmd_map[self.index]
        async with self._lock:
            self.index = (self.index + 1) % len(cmd_map)

        await self._conn.sendPacket(
            Packet(
                src=src,
                dst=dst,
                cmd_set=cmd_set,
                cmd_id=cmd_id,
                payload=b"\x00",
                version=self.packet_version,
            ),
            wait_for_response=False,
        )

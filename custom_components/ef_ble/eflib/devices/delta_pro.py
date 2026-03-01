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
from ..props import Field
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

rd_pd = dataclass_attr_mapper(DirectPdDeltaProHeartbeatPack)
rd_bms = dataclass_attr_mapper(DirectBmsMDeltaHeartbeatPack)
rd_ems = dataclass_attr_mapper(DirectEmsDeltaHeartbeatPack)
rd_inv = dataclass_attr_mapper(DirectInvDeltaHeartbeatPack)
rd_mppt = dataclass_attr_mapper(DirectMpptHeartbeatPack)
rd_kit = dataclass_attr_mapper(AllKitDetailData)


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
    battery_charge_limit_min = raw_field(rd_ems.min_dsg_soc)
    battery_charge_limit_max = raw_field(rd_ems.max_charge_soc)

    battery_1_enabled = Field[bool]()
    battery_1_battery_level = Field[float]()
    battery_1_sn = Field[str]()

    battery_2_enabled = Field[bool]()
    battery_2_battery_level = Field[float]()
    battery_2_sn = Field[str]()

    ac_output_power = raw_field(rd_inv.output_watts)
    ac_input_power = raw_field(rd_inv.input_watts)
    ac_input_voltage = raw_field(rd_inv.ac_in_vol, lambda x: round(x / 1000, 2))
    ac_input_current = raw_field(rd_inv.ac_in_amp, lambda x: round(x / 1000, 2))
    ac_ports = raw_field(rd_inv.cfg_ac_enabled, lambda x: x == 1)

    ac_charging_speed = raw_field(rd_inv.cfg_slow_chg_watts)
    max_ac_charging_power = raw_field(rd_inv.ac_chg_rated_power)

    input_power = raw_field(rd_pd.watts_in_sum)
    output_power = raw_field(rd_pd.watts_out_sum)
    dc_output_power = raw_field(rd_pd.car_watts)

    usb_ports = raw_field(rd_pd.dc_out_state, lambda x: x == 1)
    dc_12v_port = raw_field(rd_pd.car_state, lambda x: x == 1)
    energy_backup_enabled = raw_field(rd_pd.watth_is_config, lambda x: x == 1)
    energy_backup_battery_level = raw_field(rd_pd.backup_soc)

    # beep_mode: 0 = buzzer on, 1 = buzzer off (inverted in protocol)
    # buzzer = raw_field(rd_pd.beep_mode, lambda x: x == 0)

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
                kit = self.update_from_bytes(AllKitDetailData, packet.payload)
                self._update_extra_batteries(kit)

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

    def _update_extra_batteries(self, kit_data: AllKitDetailData):
        battery_entity_map = [
            {
                "enabled": Device.battery_1_enabled,
                "sn": Device.battery_1_sn,
                "level": Device.battery_1_battery_level,
            },
            {
                "enabled": Device.battery_2_enabled,
                "sn": Device.battery_2_sn,
                "level": Device.battery_2_battery_level,
            },
        ]
        for i, kit in enumerate(kit_data.kit_base_info):
            battery_dict = battery_entity_map[i]
            available = kit.avai_flag
            setattr(self, battery_dict["enabled"], bool(available))
            if available:
                setattr(self, battery_dict["sn"], kit.sn.strip(b"\x00").decode())
                setattr(self, battery_dict["level"], kit.f32_soc)

    async def _send_config_packet(self, dst: int, cmd_id: int, payload: bytes):
        await self._conn.sendPacket(
            Packet(0x21, dst, 0x20, cmd_id, payload, version=0x02)
        )

    async def enable_ac_ports(self, enabled: bool):
        payload = bytes([1 if enabled else 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        await self._send_config_packet(0x05, 0x42, payload)

    async def enable_xboost(self, enabled: bool):
        payload = bytes([0xFF, 1 if enabled else 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        await self._send_config_packet(0x05, 0x42, payload)

    async def enable_dc_12v_port(self, enabled: bool):
        await self._send_config_packet(0x05, 0x51, enabled.to_bytes())

    async def enable_usb_ports(self, enabled: bool):
        await self._send_config_packet(0x02, 0x22, enabled.to_bytes())

    async def set_battery_charge_limit_max(self, limit: int):
        await self._send_config_packet(0x03, 0x31, limit.to_bytes())

    async def set_battery_charge_limit_min(self, limit: int):
        await self._send_config_packet(0x03, 0x33, limit.to_bytes())

    async def set_ac_charging_speed(self, value: int):
        if self.max_ac_charging_power is None:
            return False
        value = max(1, min(value, self.max_ac_charging_power))
        payload = value.to_bytes(2, "little") + bytes([0xFF])
        await self._send_config_packet(0x05, 0x45, payload)
        return True

    async def enable_energy_backup(self, enabled: bool):
        backup_level = self.energy_backup_battery_level or 50
        await self.set_energy_backup_battery_level(backup_level, enabled=enabled)

    async def set_energy_backup_battery_level(self, value: int, enabled: bool = True):
        payload = bytes([0x01 if enabled else 0, value, 0x00, 0x00])
        await self._send_config_packet(0x02, 0x5E, payload)

    async def enable_solar_priority(self, enabled: bool):
        await self._send_config_packet(0x02, 0x5C, bytes([1 if enabled else 0]))

    async def set_buzzer(self, enabled: bool):
        #  0 = on, 1 = off
        await self._send_config_packet(0x05, 0x26, bytes([0 if enabled else 1]))

    async def set_screen_timeout(self, seconds: int):
        payload = bytes([seconds & 0xFF, (seconds >> 8) & 0xFF, 0xFF])
        await self._send_config_packet(0x02, 0x27, payload)

    async def set_screen_brightness(self, value: int):
        await self._send_config_packet(0x02, 0x27, bytes([0xFF, 0xFF, value]))

    async def set_ac_standby_time(self, minutes: int):
        await self._send_config_packet(0x05, 0x99, minutes.to_bytes(2, "little"))

    async def set_dc_standby_time(self, minutes: int):
        await self._send_config_packet(0x05, 0x54, minutes.to_bytes(2, "little"))

    async def set_system_standby_time(self, minutes: int):
        await self._send_config_packet(0x02, 0x21, minutes.to_bytes(2, "little"))

    async def set_car_charging_current(self, amps: int):
        await self._send_config_packet(0x05, 0x47, amps.to_bytes(4, "little"))

    async def set_dc_charging_type(self, type_id: int):
        # 0 car 1 adapter ?
        await self._send_config_packet(0x05, 0x52, bytes([type_id]))

    async def enable_ac_always_on(self, enabled: bool):
        await self._send_config_packet(0x02, 0x4A, bytes([1 if enabled else 0]))

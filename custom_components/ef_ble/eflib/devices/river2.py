from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..devicebase import DeviceBase
from ..model import (
    DirectBmsMDeltaHeartbeatPack,
    DirectEmsDeltaHeartbeatPack,
    DirectInvDeltaHeartbeatPack,
    Mr330MpptHeart,
    Mr330PdHeartRiver2,
)
from ..packet import Packet
from ..props import Field
from ..props.enums import IntFieldValue
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

pb_pd = dataclass_attr_mapper(Mr330PdHeartRiver2)
pb_mppt = dataclass_attr_mapper(Mr330MpptHeart)
pb_ems = dataclass_attr_mapper(DirectEmsDeltaHeartbeatPack)
pb_bms = dataclass_attr_mapper(DirectBmsMDeltaHeartbeatPack)
pb_inv = dataclass_attr_mapper(DirectInvDeltaHeartbeatPack)


class DCMode(IntFieldValue):
    AUTO = 0
    SOLAR = 1
    CAR = 2

    UNKNOWN = -1


class Device(DeviceBase, RawDataProps):
    """River 2"""

    NAME_PREFIX = "EF-R2"
    SN_PREFIX = (b"R601", b"R603")

    ac_ports = raw_field(pb_mppt.cfg_ac_enabled, lambda x: x == 1)
    dc_12v_port = raw_field(pb_mppt.car_state, lambda x: x == 1)
    dc12v_output_power = raw_field(pb_pd.car_watts)
    ac_xboost = raw_field(pb_mppt.cfg_ac_xboost, lambda x: x == 1)

    energy_backup = raw_field(pb_pd.watthis_config, lambda x: x == 1)
    energy_backup_battery_level = raw_field(pb_pd.bp_power_soc)

    battery_charge_limit_min = raw_field(pb_ems.min_dsg_soc)
    battery_charge_limit_max = raw_field(pb_ems.max_charge_soc)

    battery_level = raw_field(pb_bms.f32_show_soc, lambda x: round(x, 2))
    cell_temperature = raw_field(pb_bms.temp)

    input_power = raw_field(pb_pd.watts_in_sum)
    output_power = raw_field(pb_pd.watts_out_sum)
    ac_input_power = raw_field(pb_inv.input_watts)
    ac_output_power = raw_field(pb_inv.output_watts)

    dc_mode = raw_field(pb_mppt.cfg_chg_type, DCMode.from_value)

    dc_port_input_power = raw_field(pb_mppt.in_watts)
    solar_input_power = Field[int]()
    car_input_power = Field[int]()

    usbc_output_power = raw_field(pb_pd.typec1_watts)
    usba_output_power = raw_field(pb_pd.usb1_watt)

    dc_charging_max_amps = raw_field(pb_mppt.cfg_dc_chg_current, lambda x: x / 1000)
    dc_charging_current_max = Field[int]()

    ac_charging_speed = raw_field(pb_mppt.cfg_chg_watts)
    max_ac_charging_power = Field[int]()
    min_ac_charging_power = Field[int]()

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self.dc_charging_current_max = 8
        self.min_ac_charging_power = 100
        self.max_ac_charging_power = 940

    @classmethod
    def check(cls, sn: bytes):
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self):
        match self._sn[:4]:
            case "R601" | "R603":
                return "River 2"
            case "R621" | "R623":
                return "River 2 Pro"
            case "R611" | "R613":
                return "River 2 Max"
        return "River 2"

    @property
    def packet_version(self):
        return 2

    async def data_parse(self, packet: Packet) -> bool:
        self.reset_updated()
        processed = False

        match (packet.src, packet.cmdSet, packet.cmdId):
            case 0x02, 0x20, 0x02:
                self.update_from_bytes(Mr330PdHeartRiver2, packet.payload)
                processed = True

            case 0x03, 0x20, 0x02:
                self.update_from_bytes(DirectEmsDeltaHeartbeatPack, packet.payload)
                processed = True

            case 0x03, 0x20, 0x32:
                self.update_from_bytes(DirectBmsMDeltaHeartbeatPack, packet.payload)
                processed = True

            case 0x04, _, 0x02:
                self.update_from_bytes(DirectInvDeltaHeartbeatPack, packet.payload)
                processed = True

            case 0x05, 0x20, 0x02:
                self.update_from_bytes(Mr330MpptHeart, packet.payload)
                self.car_input_power = (
                    self.dc_port_input_power if self.dc_mode == DCMode.CAR else 0
                )
                self.solar_input_power = (
                    self.dc_port_input_power if self.dc_mode == DCMode.SOLAR else 0
                )

                processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name, None))

        return processed

    async def enable_ac_ports(self, enabled: bool):
        payload = bytes([1 if enabled else 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        packet = Packet(0x21, 0x05, 0x20, 0x42, payload, version=2)
        await self._conn.sendPacket(packet)

    async def enable_dc_12v_port(self, enabled: bool):
        payload = bytes([0x01 if enabled else 0x00])
        packet = Packet(0x21, 0x05, 0x20, 0x51, payload, version=2)
        await self._conn.sendPacket(packet)

    async def enable_ac_xboost(self, enabled: bool):
        payload = bytes([0xFF, 0x01 if enabled else 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        packet = Packet(0x21, 0x05, 0x20, 0x42, payload, version=2)
        await self._conn.sendPacket(packet)

    async def enable_ac_always_on(self, enabled: bool):
        payload = bytes([0x01 if enabled else 0x00, 0x05])
        packet = Packet(0x21, 0x02, 0x20, 0x5F, payload, version=2)
        await self._conn.sendPacket(packet)

    async def enable_energy_backup(self, enabled: bool):
        reserve = (
            self.energy_backup_battery_level
            if self.energy_backup_battery_level is not None
            else 30
        )
        reserve = max(0, min(int(reserve), 100))

        payload = bytes([0x01 if enabled else 0x00, reserve, 0x00, 0x00])
        packet = Packet(0x21, 0x02, 0x20, 0x5E, payload, version=2)
        await self._conn.sendPacket(packet)

    async def set_energy_backup_battery_level(self, value: int) -> bool:
        percent = max(0, min(int(value), 100))
        payload = bytes([0x01, percent, 0x00, 0x00])
        packet = Packet(0x21, 0x02, 0x20, 0x5E, payload, version=2)
        await self._conn.sendPacket(packet)
        return True

    async def set_battery_charge_limit_min(self, limit: int) -> bool:
        limit = max(0, min(int(limit), 30))
        if (
            self.battery_charge_limit_max is not None
            and limit > self.battery_charge_limit_max
        ):
            return False

        packet = Packet(0x21, 0x03, 0x20, 0x33, limit.to_bytes(), version=2)
        await self._conn.sendPacket(packet)
        return True

    async def set_battery_charge_limit_max(self, limit: int) -> bool:
        if self.battery_charge_limit_min is not None and limit < int(
            self.battery_charge_limit_min
        ):
            return False

        packet = Packet(0x21, 0x03, 0x20, 0x31, limit.to_bytes(), version=2)
        await self._conn.sendPacket(packet)
        return True

    async def set_dc_charging_amps_max(self, value: int) -> bool:
        packet = Packet(0x21, 0x05, 0x20, 0x47, value.to_bytes(), version=2)
        await self._conn.sendPacket(packet)
        return True

    async def set_dc_mode(self, value: DCMode) -> bool:
        packet = Packet(0x21, 0x05, 0x20, 0x52, value.to_bytes(), version=2)
        await self._conn.sendPacket(packet)
        return True

    async def set_ac_charging_speed(self, value: int):
        payload = value.to_bytes(2, "little") + b"\xff"
        packet = Packet(0x21, 0x05, 0x20, 0x45, payload, version=2)
        await self._conn.sendPacket(packet)
        return True

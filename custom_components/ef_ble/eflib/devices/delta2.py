from ..devicebase import DeviceBase
from ..model import (
    AllKitDetailData,
    DirectBmsMDeltaHeartbeatPack,
    DirectEmsDeltaHeartbeatPack,
    DirectInvDelta2HeartbeatPack,
    Mr330MpptHeart,
    Mr330PdHeart,
)
from ..packet import Packet
from ..props import Field
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps


class _BmsHeartbeatBattery1(DirectBmsMDeltaHeartbeatPack):
    pass


pb_pd = dataclass_attr_mapper(Mr330PdHeart)
pb_mppt = dataclass_attr_mapper(Mr330MpptHeart)
pb_ems = dataclass_attr_mapper(DirectEmsDeltaHeartbeatPack)
pb_bms = dataclass_attr_mapper(DirectBmsMDeltaHeartbeatPack)
pb_bms_1 = dataclass_attr_mapper(_BmsHeartbeatBattery1)
pb_inv = dataclass_attr_mapper(DirectInvDelta2HeartbeatPack)


class Device(DeviceBase, RawDataProps):
    """Delta 2"""

    SN_PREFIX = (b"R331", b"R335")
    NAME_PREFIX = "EF-R33"

    @property
    def packet_version(self):
        return 2

    ac_output_power = raw_field(pb_inv.output_watts)
    ac_input_power = raw_field(pb_pd.ac_input_watts)
    plugged_in_ac = raw_field(pb_pd.ac_charge_flag, lambda x: x == 1)

    battery_level_main = raw_field(pb_bms.f32_show_soc, lambda x: round(x, 2))
    battery_1_battery_level = raw_field(pb_bms_1.f32_show_soc, lambda x: round(x, 2))
    # battery_level = Field[float]()
    battery_level = raw_field(pb_ems.f32_lcd_show_soc, lambda x: round(x, 2))

    master_design_cap = raw_field(pb_bms.design_cap)
    master_remain_cap = raw_field(pb_bms.remain_cap)
    master_full_cap = raw_field(pb_bms.full_cap)
    slave_design_cap = raw_field(pb_bms_1.design_cap)
    slave_remain_cap = raw_field(pb_bms_1.remain_cap)
    slave_full_cap = raw_field(pb_bms_1.full_cap)
    battery_addon = Field[bool]()

    energy_backup_battery_level = raw_field(pb_pd.bp_power_soc)

    input_power = raw_field(pb_pd.watts_in_sum)
    output_power = raw_field(pb_pd.watts_out_sum)

    usbc_output_power = raw_field(pb_pd.typec1_watts)
    usba_output_power = raw_field(pb_pd.usb1_watt)

    usb_ports = raw_field(pb_pd.dc_out_state, lambda x: x == 1)

    battery_charge_limit_min = raw_field(pb_ems.min_dsg_soc)
    battery_charge_limit_max = raw_field(pb_ems.max_charge_soc)

    cell_temperature = raw_field(pb_pd.car_temp)

    dc_12v_port = raw_field(pb_pd.car_state, lambda x: x == 1)
    dc_output_power = raw_field(pb_pd.dc_pv_output_watts)
    dc12v_output_voltage = raw_field(pb_mppt.car_out_vol, lambda x: round(x / 1000, 2))
    dc12v_output_current = raw_field(pb_mppt.car_out_amp, lambda x: round(x / 1000, 2))

    ac_charging_speed = raw_field(pb_mppt.cfg_chg_watts)
    max_ac_charging_power = Field[int]()

    ac_ports = raw_field(pb_pd.cfg_ac_enabled, lambda x: x == 1)

    def __init__(self, ble_dev, adv_data, sn: str) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._product_type: int | None = None
        self.max_ac_charging_power = 1200
        self.battery_addon = False

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self):
        model = "2"
        match self._sn[:4]:
            case "D361":
                model = "3 1500"
            case "R351" | "R354":
                model = "2 Max"

        return f"Delta {model}"

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet) -> bool:
        """Process the incoming notifications from the device"""

        processed = False
        self.reset_updated()

        match packet.src, packet.cmdSet, packet.cmdId:
            case 0x02, 0x20, 0x02:
                self.update_from_bytes(Mr330PdHeart, packet.payload)
                processed = True
            case 0x03, 0x03, 0x0E:
                detail = self.update_from_bytes(AllKitDetailData, packet.payload)
                self._update_product_type(detail)
                processed = True
            case 0x03, 0x20, 0x02:
                self.update_from_bytes(DirectEmsDeltaHeartbeatPack, packet.payload)
                processed = True
            case 0x03, 0x20, 0x32:
                self.update_from_bytes(DirectBmsMDeltaHeartbeatPack, packet.payload)
                processed = True
            case 0x06, 0x20, 0x32:
                self.update_from_bytes(_BmsHeartbeatBattery1, packet.payload)
                processed = True
            case 0x04, _, 0x02:
                self.update_from_bytes(DirectInvDelta2HeartbeatPack, packet.payload)
                processed = True
            case 0x05, 0x20, 0x02:
                self.update_from_bytes(Mr330MpptHeart, packet.payload)
                processed = True

        if processed:
            if self.battery_1_battery_level is not None:
                self.battery_addon = True

            self._update_ac_chg_limits()

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def set_battery_charge_limit_max(self, limit: int):
        packet = Packet(0x21, 0x03, 0x20, 0x31, limit.to_bytes(), version=0x02)
        await self._conn.sendPacket(packet)

    async def set_battery_charge_limit_min(self, limit: int):
        packet = Packet(0x21, 0x03, 0x20, 0x33, limit.to_bytes(), version=0x02)
        await self._conn.sendPacket(packet)

    async def set_ac_charging_speed(self, value: int):
        if self.max_ac_charging_power is None:
            return

        value = max(1, min(value, self.max_ac_charging_power))
        # Sending 0 sets to (more than) max-load - better safe

        payload = value.to_bytes(2, "little") + bytes([0xFF])
        if self._is_mr530():
            payload = bytes([0xFF, 0xFF]) + payload

        packet = Packet(
            0x21,
            (0x04 if self._is_mr530() else 0x05),
            0x20,
            0x45,
            payload,
            version=0x02,
        )
        await self._conn.sendPacket(packet)

    async def set_energy_backup_battery_level(self, value: int):
        if (
            self.battery_charge_limit_min is None
            or self.battery_charge_limit_max is None
        ):
            return

        value = max(
            self.battery_charge_limit_min,
            min(value, self.battery_charge_limit_max),
        )
        payload = bytes([0x01]) + value.to_bytes() + bytes([0x00, 0x00])
        packet = Packet(0x21, 0x02, 0x20, 0x5E, payload, version=0x02)
        await self._conn.sendPacket(packet)

    async def enable_usb_ports(self, enabled: bool):
        packet = Packet(0x21, 0x02, 0x20, 0x22, enabled.to_bytes(), version=0x02)
        await self._conn.sendPacket(packet)

    async def enable_dc_12v_port(self, enabled: bool):
        packet = Packet(
            0x21,
            (0x07 if self._is_mr530() else 0x05),
            0x20,
            0x51,
            enabled.to_bytes(),
            version=0x02,
        )
        await self._conn.sendPacket(packet)

    async def enable_ac_ports(self, enabled: bool):
        payload = bytes([1 if enabled else 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        packet = Packet(0x21, 0x05, 0x20, 0x42, payload, version=0x02)
        await self._conn.sendPacket(packet)

    def _update_product_type(self, detail: AllKitDetailData) -> None:
        if not detail.kit_base_info:
            return

        sn_bytes = self._sn.encode()
        for kit in detail.kit_base_info:
            if kit.sn.rstrip(b"\x00") == sn_bytes:
                self._product_type = kit.product_type
                return

        self._product_type = detail.kit_base_info[0].product_type

    def _update_ac_chg_limits(self) -> None:
        if self.battery_addon:
            self.max_ac_charging_power = 1500
        else:
            self.max_ac_charging_power = 1200

    def _is_mr530(self) -> bool:
        return self._product_type == 82

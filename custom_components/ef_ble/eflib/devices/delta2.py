from ..devicebase import DeviceBase
from ..model import (
    AllKitDetailData,
    DirectBmsMDeltaHeartbeatPack,
    DirectEmsDeltaHeartbeatPack,
    DirectMpptHeartbeatPack,
    Mr330MpptHeart,
    Mr330PdHeart,
)
from ..packet import Packet
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

pb_pd = dataclass_attr_mapper(Mr330PdHeart)
pb_mppt = dataclass_attr_mapper(DirectMpptHeartbeatPack)
pb_ems = dataclass_attr_mapper(DirectEmsDeltaHeartbeatPack)
pb_bms = dataclass_attr_mapper(DirectBmsMDeltaHeartbeatPack)


class Device(DeviceBase, RawDataProps):
    """Delta 2"""

    SN_PREFIX = (b"R331", b"R335", b"D361")
    NAME_PREFIX = "EF-R33"

    @property
    def packet_version(self):
        return 2

    ac_output_power = raw_field(pb_pd.ac_dsg_power)
    ac_input_power = raw_field(pb_pd.ac_input_watts)
    plugged_in_ac = raw_field(pb_pd.ac_charge_flag, lambda x: x == 1)

    battery_level = raw_field(pb_bms.f32_show_soc, lambda x: round(x, 2))
    input_power = raw_field(pb_pd.watts_in_sum)
    output_power = raw_field(pb_pd.watts_out_sum)

    usbc_output_power = raw_field(pb_pd.typec1_watts)
    usba_output_power = raw_field(pb_pd.usb1_watt)

    usb_ports = raw_field(pb_pd.dc_out_state, lambda x: x == 1)

    battery_charge_limit_min = raw_field(pb_ems.min_dsg_soc)
    battery_charge_limit_max = raw_field(pb_ems.max_charge_soc)

    cell_temperature = raw_field(pb_pd.car_temp)

    dc_12v_port = raw_field(pb_mppt.car_state, lambda x: x == 1)
    dc_output_power = raw_field(pb_pd.dc_pv_output_watts)
    dc12v_output_voltage = raw_field(pb_mppt.car_out_vol, lambda x: round(x / 1000, 2))
    dc12v_output_current = raw_field(pb_mppt.car_out_amp, lambda x: round(x / 1000, 2))

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self):
        model = "2"
        match self._sn[:4]:
            case "D361":
                model = "3 1500"

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
                self.update_from_bytes(AllKitDetailData, packet.payload)
                processed = True
            case 0x03, 0x20, 0x02:
                self.update_from_bytes(DirectEmsDeltaHeartbeatPack, packet.payload)
                processed = True
            case 0x03, 0x20, 0x32:
                self.update_from_bytes(DirectBmsMDeltaHeartbeatPack, packet.payload)
                processed = True
            # case 0x04, _, 0x02:
            #     self.update_from_bytes(DirectInvDeltaHeartbeatPack, packet.payload)
            #     processed = True
            case 0x05, 0x20, 0x02:
                self.update_from_bytes(Mr330MpptHeart, packet.payload)
                processed = True

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

    async def enable_usb_ports(self, enabled: bool):
        packet = Packet(0x21, 0x02, 0x20, 0x22, enabled.to_bytes(), version=0x02)
        await self._conn.sendPacket(packet)

    async def enable_dc_12v_port(self, enabled: bool):
        packet = Packet(0x21, 0x05, 0x20, 0x51, enabled.to_bytes(), version=0x02)
        await self._conn.sendPacket(packet)

    async def enable_ac_ports(self, enabled: bool):
        payload = bytes([1 if enabled else 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        packet = Packet(0x21, 0x05, 0x20, 0x42, payload, version=0x02)
        await self._conn.sendPacket(packet)

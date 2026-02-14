import time

from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import bk622_common_pb2
from ..props import (
    ProtobufProps,
    pb_field,
    proto_attr_mapper,
)
from ..props.enums import IntFieldValue

pb = proto_attr_mapper(bk622_common_pb2.DisplayPropertyUpload)


class GridState(IntFieldValue):
    NOT_VALID = 0
    GRID_IN = 1
    GRID_OFFLINE = 2
    FEED_GRID = 3


def _round2(value: float):
    return round(value, 2)


class Device(DeviceBase, ProtobufProps):
    SN_PREFIX = (b"BK21",)
    NAME_PREFIX = "EF-WN2"

    @classmethod
    def check(cls, sn: bytes):
        return sn[:4] in cls.SN_PREFIX

    grid_power = pb_field(pb.pow_get_sys_grid)
    grid_state = pb_field(pb.grid_connection_sta, GridState.from_value)
    grid_energy = pb_field(pb.grid_connection_data_record.today_active)

    l1_active = pb_field(pb.grid_connection_flag_L1)
    l1_power = pb_field(pb.grid_connection_power_L1, _round2)
    l1_current = pb_field(pb.grid_connection_amp_L1, _round2)
    l1_voltage = pb_field(pb.grid_connection_vol_L1, _round2)
    l1_grid_energy = pb_field(pb.grid_connection_data_record.today_active_L1)

    l2_active = pb_field(pb.grid_connection_flag_L2)
    l2_power = pb_field(pb.grid_connection_power_L2, _round2)
    l2_current = pb_field(pb.grid_connection_amp_L2, _round2)
    l2_voltage = pb_field(pb.grid_connection_vol_L2, _round2)
    l2_grid_energy = pb_field(pb.grid_connection_data_record.today_active_L2)

    l3_active = pb_field(pb.grid_connection_flag_L3)
    l3_power = pb_field(pb.grid_connection_power_L3, _round2)
    l3_current = pb_field(pb.grid_connection_amp_L3, _round2)
    l3_voltage = pb_field(pb.grid_connection_vol_L3, _round2)
    l3_grid_energy = pb_field(pb.grid_connection_data_record.today_active_L3)

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet):
        processed = False
        self.reset_updated()

        match packet.src, packet.cmdSet, packet.cmdId:
            case (0x02, 0xFE, 0x15):
                self.update_from_bytes(
                    bk622_common_pb2.DisplayPropertyUpload, packet.payload
                )
                processed = True

        if not self.l1_active:
            self.l1_power = self.l1_current = self.l1_voltage = 0
        if not self.l2_active:
            self.l2_power = self.l2_current = self.l2_voltage = 0
        if not self.l3_active:
            self.l3_power = self.l3_current = self.l3_voltage = 0

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def _send_config_packet(self, message: bk622_common_pb2.ConfigWrite):
        payload = message.SerializeToString()
        message.cfg_utc_time = round(time.time())
        packet = Packet(0x20, 0x02, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

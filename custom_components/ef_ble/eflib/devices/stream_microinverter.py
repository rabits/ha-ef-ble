import time

from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import bk_series_pb2
from ..props import ProtobufProps, pb_field, proto_attr_mapper
from ..props.enums import IntFieldValue
from ..props.transforms import pround

pb = proto_attr_mapper(bk_series_pb2.DisplayPropertyUpload)


class GridStatus(IntFieldValue):
    UNKNOWN = -1

    NOT_VALID = 0
    GRID_IN = 1
    GRID_OFFLINE = 2
    FEED_GRID = 3


class Device(DeviceBase, ProtobufProps):
    """STREAM Microinverter"""

    SN_PREFIX = (b"BK01", b"BK02", b"N011")
    NAME_PREFIX = "EF-BK"

    pv_power_1 = pb_field(pb.pow_get_pv, pround(2))
    pv_voltage_1 = pb_field(pb.plug_in_info_pv_vol, pround(1))
    pv_current_1 = pb_field(pb.plug_in_info_pv_amp, pround(2))

    pv_power_2 = pb_field(pb.pow_get_pv2, pround(2))
    pv_voltage_2 = pb_field(pb.plug_in_info_pv2_vol, pround(1))
    pv_current_2 = pb_field(pb.plug_in_info_pv2_amp, pround(2))

    grid_power = pb_field(pb.grid_connection_power)
    grid_voltage = pb_field(pb.grid_connection_vol, pround(2))
    grid_current = pb_field(pb.grid_connection_amp, pround(2))
    grid_frequency = pb_field(pb.grid_connection_freq, pround(2))
    grid_connection_status = pb_field(pb.grid_connection_sta, GridStatus.from_value)

    wifi_rssi = pb_field(pb.module_wifi_rssi, pround(0))
    feed_grid_mode_power_limit = pb_field(pb.feed_grid_mode_pow_limit)
    feed_grid_mode_power_max = pb_field(pb.feed_grid_mode_pow_max)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet):
        processed = False
        self.reset_updated()

        if packet.src == 0x02 and packet.cmdSet == 0xFE and packet.cmdId == 0x15:
            self.update_from_bytes(bk_series_pb2.DisplayPropertyUpload, packet.payload)
            processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def _send_config_packet(self, message: bk_series_pb2.ConfigWrite):
        payload = message.SerializeToString()
        message.cfg_utc_time = round(time.time())
        packet = Packet(0x20, 0x02, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

    async def set_inverter_target_power(self, power: int):
        if power < 0:
            return False

        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_inv_target_pwr=power)
        )
        return True

    async def set_feed_grid_mode_pow_limit(self, power: int):
        if (
            power < 0
            or self.feed_grid_mode_power_max is None
            or power > self.feed_grid_mode_power_max
        ):
            return False

        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_feed_grid_mode_pow_limit=power)
        )
        return True

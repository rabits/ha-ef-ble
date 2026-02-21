import logging

from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import wn511_sys_pb2
from ..props import ProtobufProps, pb_field, proto_attr_mapper

_LOGGER = logging.getLogger(__name__)

pb = proto_attr_mapper(wn511_sys_pb2.inverter_heartbeat)


def _div10(value):
    return round(value / 10, 1)


class Device(DeviceBase, ProtobufProps):
    """PowerStream"""

    SN_PREFIX = (b"HW51",)
    NAME_PREFIX = "EF-HW"

    pv_power_1 = pb_field(pb.pv1_input_watts, _div10)
    pv_voltage_1 = pb_field(pb.pv1_input_volt, _div10)
    pv_current_1 = pb_field(pb.pv1_input_cur, _div10)
    pv_temperature_1 = pb_field(pb.pv1_temp, _div10)

    pv_power_2 = pb_field(pb.pv2_input_watts, _div10)
    pv_voltage_2 = pb_field(pb.pv2_input_volt, _div10)
    pv_current_2 = pb_field(pb.pv2_input_cur, _div10)
    pv_temperature_2 = pb_field(pb.pv2_temp, _div10)

    battery_level = pb_field(pb.bat_soc)
    battery_power = pb_field(pb.bat_input_watts, _div10)
    battery_temperature = pb_field(pb.bat_temp, _div10)

    grid_power = pb_field(pb.inv_output_watts, _div10)
    grid_voltage = pb_field(pb.inv_op_volt, _div10)
    grid_current = pb_field(pb.inv_output_cur, _div10)
    grid_frequency = pb_field(pb.inv_freq, _div10)
    inverter_temperature = pb_field(pb.inv_temp, _div10)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    _HEARTBEAT_INTERVAL = 30
    _REPLY_INTERVAL = 10

    def __init__(self, ble_dev, adv_data, sn):
        super().__init__(ble_dev, adv_data, sn)
        # self._last_reply_time = 0.0
        self.add_timer_task(self._request_heartbeat, interval=self._HEARTBEAT_INTERVAL)

    async def _request_heartbeat(self):
        await self._conn.send_auth_status_packet()

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet) -> bool:
        self.reset_updated()

        match packet.src, packet.cmdSet, packet.cmdId:
            case (0x35, 0x14, 0x01):
                self.update_from_bytes(wn511_sys_pb2.inverter_heartbeat, packet.payload)
            case (0x35, 0x14, 0x04):
                self.update_from_bytes(
                    wn511_sys_pb2.inv_heartbeat_type2, packet.payload
                )
            case _:
                return False

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return True

    # async def _handle_type2_heartbeat(self, packet: Packet) -> bool:
    #     """Parse inv_heartbeat_type2 (cmdId=0x04) and reply to keep data flowing."""
    #     # Throttled reply to keep the device sending data (DPU pattern).
    #     now = time.monotonic()
    #     if now - self._last_reply_time >= self._REPLY_INTERVAL:
    #         self._last_reply_time = now
    #         with contextlib.suppress(Exception):
    #             await self._conn.replyPacket(packet)

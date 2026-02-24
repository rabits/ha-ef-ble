import time

from google.protobuf.message import Message

from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import wn511_sys_pb2
from ..props import Field, ProtobufProps, pb_field, proto_attr_mapper
from ..props.enums import IntFieldValue

pb = proto_attr_mapper(wn511_sys_pb2.inverter_heartbeat)
pb_inv2 = proto_attr_mapper(wn511_sys_pb2.inv_heartbeat_type2)


def _div10(value):
    return round(value / 10, 1)


class PowerSupplyPriority(IntFieldValue):
    UNKNOWN = -1

    POWER_SUPPLY = 0
    POWER_STORAGE = 1


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

    battery_level = pb_field(
        pb_inv2.new_psdr_heartbeat.f32_lcd_show_soc, lambda x: round(x, 2)
    )
    battery_power = pb_field(pb.bat_input_watts, _div10)
    battery_temperature = pb_field(pb.bat_temp, _div10)

    inverter_power = pb_field(pb.inv_output_watts, _div10)
    inverter_voltage = pb_field(pb.inv_op_volt, _div10)
    inverter_current = pb_field(pb.inv_output_cur, lambda x: round(x / 1000, 2))
    inverter_frequency = pb_field(pb.inv_freq, _div10)
    inverter_temperature = pb_field(pb.inv_temp, _div10)

    battery_charge_limit_max = pb_field(pb.upper_limit)
    battery_charge_limit_min = pb_field(pb.lower_limit)
    power_supply_priority = pb_field(pb.supply_priority, PowerSupplyPriority.from_value)

    load_power_max = Field[int]()
    load_power = pb_field(pb.permanent_watts, _div10)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    _HEARTBEAT_INTERVAL = 30
    _REPLY_INTERVAL = 10

    _DST_INVERTER = 0x35
    _DST_DISPLAY = 0x14

    def __init__(self, ble_dev, adv_data, sn):
        super().__init__(ble_dev, adv_data, sn)
        self.add_timer_task(self._request_heartbeat, interval=self._HEARTBEAT_INTERVAL)
        self.load_power_max = 800
        self._heartbeat2_last_reply_time = 0

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
                now = time.monotonic()
                if now - self._heartbeat2_last_reply_time >= self._REPLY_INTERVAL:
                    self._heartbeat2_last_reply_time = now
                    await self._conn.replyPacket(packet)

            case (0x35, 0x14, 0x88):
                inv_power = self.update_from_bytes(
                    wn511_sys_pb2.inv_power_pack, packet.payload
                )
                await self._send_ble_packet(
                    wn511_sys_pb2.inv_power_pack_ack(sys_seq=inv_power.sys_seq),
                    cmd_id=0x88,
                )
            case _:
                return False

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return True

    async def _send_ble_packet(
        self, message: Message, cmd_id: int, dst: int = _DST_INVERTER
    ) -> None:
        payload = message.SerializeToString()
        packet = Packet(0x21, dst, 0x14, cmd_id, payload, version=0x13)
        await self._conn.sendPacket(packet)

    async def set_load_power(self, watts: float) -> bool:
        await self._send_ble_packet(
            wn511_sys_pb2.permanent_watts_pack(permanent_watts=int(watts * 10)),
            cmd_id=0x81,
        )
        return True

    async def set_supply_priority(self, priority: PowerSupplyPriority) -> bool:
        await self._send_ble_packet(
            wn511_sys_pb2.supply_priority_pack(supply_priority=priority.value),
            cmd_id=0x82,
        )
        return True

    async def set_battery_charge_limit_min(self, limit: int) -> bool:
        limit = max(0, min(limit, 30))

        await self._send_ble_packet(
            wn511_sys_pb2.bat_lower_pack(lower_limit=limit),
            cmd_id=0x84,
        )
        return True

    async def set_battery_charge_limit_max(self, limit: int) -> bool:
        limit = max(50, min(limit, 100))

        await self._send_ble_packet(
            wn511_sys_pb2.bat_upper_pack(upper_limit=limit),
            cmd_id=0x85,
        )
        return True

    async def set_brightness(self, brightness: int) -> bool:
        clamped = max(0, min(1023, brightness))

        await self._send_ble_packet(
            wn511_sys_pb2.brightness_pack(brightness=clamped),
            cmd_id=0x87,
        )
        return True

    async def set_feed_protect(self, value: int) -> bool:
        await self._send_ble_packet(
            wn511_sys_pb2.feed_protect_pack(feed_protect=value),
            cmd_id=0x8F,
        )
        return True

    async def set_ac_max_watts(self, max_watts: int) -> bool:
        await self._send_ble_packet(
            wn511_sys_pb2.AC_max_watts_pack(AC_max_watts=max_watts),
            cmd_id=0x92,
            dst=self._DST_DISPLAY,
        )
        return True

    async def set_ac_watts(self, set_watts: int, max_watts: int) -> bool:
        await self._send_ble_packet(
            wn511_sys_pb2.AC_max_watts_pack(
                AC_set_watts=set_watts, AC_max_watts=max_watts
            ),
            cmd_id=0x92,
            dst=self._DST_DISPLAY,
        )
        return True

import contextlib
import logging
import time

from google.protobuf.message import DecodeError

from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import wn511_sys_pb2
from ..props import ProtobufProps, pb_field, proto_attr_mapper
from ..ps_connection import PowerStreamConnection

_LOGGER = logging.getLogger(__name__)

pb = proto_attr_mapper(wn511_sys_pb2.inverter_heartbeat)


def _div10(value):
    return round(value / 10, 1)


class Device(DeviceBase, ProtobufProps):
    """PowerStream 600W"""

    SN_PREFIX = (b"HW51",)
    NAME_PREFIX = "EF-HW"
    _packet_version = 0x03
    _REPLY_INTERVAL = 10

    # Solar Panel 1
    pv_power_1 = pb_field(pb.pv1_input_watts, _div10)
    pv_voltage_1 = pb_field(pb.pv1_input_volt, _div10)
    pv_current_1 = pb_field(pb.pv1_input_cur, _div10)
    pv_temperature_1 = pb_field(pb.pv1_temp, _div10)

    # Solar Panel 2
    pv_power_2 = pb_field(pb.pv2_input_watts, _div10)
    pv_voltage_2 = pb_field(pb.pv2_input_volt, _div10)
    pv_current_2 = pb_field(pb.pv2_input_cur, _div10)
    pv_temperature_2 = pb_field(pb.pv2_temp, _div10)

    # Battery
    battery_level = pb_field(pb.bat_soc)
    battery_power = pb_field(pb.bat_input_watts, _div10)
    battery_temperature = pb_field(pb.bat_temp, _div10)

    # Inverter output (grid feed)
    grid_power = pb_field(pb.inv_output_watts, _div10)
    grid_voltage = pb_field(pb.inv_op_volt, _div10)
    grid_current = pb_field(pb.inv_output_cur, _div10)
    grid_frequency = pb_field(pb.inv_freq, _div10)
    inverter_temperature = pb_field(pb.inv_temp, _div10)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    def __init__(self, ble_dev, adv_data, sn):
        super().__init__(ble_dev, adv_data, sn)
        self._cmd_counts = {}
        self._last_reply_time = 0.0

    def _create_connection(self, **kwargs):
        return PowerStreamConnection(**kwargs)

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        self.reset_updated()

        if packet.cmdSet == 0x14:
            cmd_key = f"0x{packet.cmdId:02x}"
            self._cmd_counts[cmd_key] = self._cmd_counts.get(cmd_key, 0) + 1
            if self._cmd_counts[cmd_key] <= 3:
                _LOGGER.info(
                    "cmd=0x14/0x%02x len=%d (count=%d)",
                    packet.cmdId,
                    len(packet.payload),
                    self._cmd_counts[cmd_key],
                )

            if packet.cmdId == 0x01:
                try:
                    msg = wn511_sys_pb2.inverter_heartbeat()
                    msg.ParseFromString(packet.payload)
                    self.update_from_message(msg)
                    processed = True
                    _LOGGER.debug(
                        "Heartbeat decoded: bat_soc=%s inv_op_volt=%s",
                        msg.bat_soc,
                        msg.inv_op_volt,
                    )
                except DecodeError as e:
                    _LOGGER.warning("Heartbeat DecodeError: %s", e)

            elif packet.cmdId == 0x04:
                processed = await self._handle_type2_heartbeat(packet)

            else:
                processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def _handle_type2_heartbeat(self, packet: Packet) -> bool:
        """Parse inv_heartbeat_type2 (cmdId=0x04) and reply to keep data flowing."""
        # Throttled reply to keep the device sending data (DPU pattern).
        now = time.monotonic()
        if now - self._last_reply_time >= self._REPLY_INTERVAL:
            self._last_reply_time = now
            with contextlib.suppress(Exception):
                await self._conn.replyPacket(packet)

        count = self._cmd_counts.get("0x04", 0)

        # Log hex dump of first payload for debugging
        if count == 1:
            _LOGGER.info(
                "cmdId=0x04 payload hex (%d bytes): %s",
                len(packet.payload),
                packet.payload.hex(),
            )

        try:
            msg = wn511_sys_pb2.inv_heartbeat_type2()
            msg.ParseFromString(packet.payload)
        except DecodeError as e:
            if count <= 3:
                _LOGGER.warning(
                    "Type2 heartbeat DecodeError: %s (len=%d)",
                    e,
                    len(packet.payload),
                )
            return False

        if count <= 3:
            _LOGGER.info(
                "Type2 HB: permanent_watts=%s dynamic_watts=%s "
                "upper_limit=%s lower_limit=%s ac_is_ok=%s",
                msg.permanent_watts,
                msg.dynamic_watts,
                msg.upper_limit,
                msg.lower_limit,
                msg.ac_is_ok,
            )

        # Extract battery module data from nested message
        if msg.HasField("new_psdr_heartbeat"):
            bp = msg.new_psdr_heartbeat
            if count <= 3:
                _LOGGER.info(
                    "Battery module: soc=%s vol=%s amp=%s temp=%s "
                    "input_watts=%s output_watts=%s cycles=%s",
                    bp.soc,
                    bp.vol,
                    bp.amp,
                    bp.temp,
                    bp.input_watts,
                    bp.output_watts,
                    bp.cycles,
                )

        return True

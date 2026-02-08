from google.protobuf.message import DecodeError

from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import wn511_sys_pb2
from ..props import ProtobufProps, pb_field, proto_attr_mapper
from ..ps_connection import PowerStreamConnection

pb = proto_attr_mapper(wn511_sys_pb2.inverter_heartbeat)


def _div10(value):
    return round(value / 10, 1)


class Device(DeviceBase, ProtobufProps):
    """PowerStream 600W"""

    SN_PREFIX = (b"HW51",)
    NAME_PREFIX = "EF-HW"
    _packet_version = 0x02

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

    def _create_connection(self, **kwargs):
        return PowerStreamConnection(**kwargs)

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        self.reset_updated()

        if packet.cmdSet == 0x14 and packet.cmdId == 0x01:
            try:
                self.update_from_bytes(
                    wn511_sys_pb2.inverter_heartbeat, packet.payload
                )
                processed = True
            except DecodeError:
                pass

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

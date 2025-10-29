import logging

from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import ac517_apl_comm_pb2
from ..props import ProtobufProps, pb_field
from ..props.enums import IntFieldValue
from ..props.utils import pround
from .alternator_charger import proto_attr_mapper

pb = proto_attr_mapper(ac517_apl_comm_pb2.DisplayPropertyUpload)
pb_run  = proto_attr_mapper(ac517_apl_comm_pb2.RuntimePropertyUpload)

_LOGGER = logging.getLogger(__name__)


class OperatingMode(IntFieldValue):
    UNKNOWN = -1

    NULL = 0
    COOLING = 1
    HEATING = 2
    VENTING = 3
    DEHUMIDIFYING = 4
    THERMOSTATIC = 5


class TemperatureUnit(IntFieldValue):
    UNKNOWN = -1

    NONE = 0
    CELSIUS = 1
    FAHRENHEIT = 2

    @classmethod
    def from_mode(cls, mode: ac517_apl_comm_pb2.USER_TEMP_UNIT_TYPE):
        try:
            return cls(mode)
        except ValueError:
            _LOGGER.debug("Encountered invalid value %s for %s", mode, cls.__name__)
            return TemperatureUnit.UNKNOWN

    def as_pb_enum(self):
        return {
            TemperatureUnit.NONE: ac517_apl_comm_pb2.USER_TEMP_UNIT_NONE,
            TemperatureUnit.CELSIUS: ac517_apl_comm_pb2.USER_TEMP_UNIT_C,
            TemperatureUnit.FAHRENHEIT: ac517_apl_comm_pb2.USER_TEMP_UNIT_F,
        }[self]


class Device(DeviceBase, ProtobufProps):
    """Wave 3"""

    SN_PREFIX = (b"AC71",)
    NAME_PREFIX = "EF-AC"

    battery_level = pb_field(pb.cms_batt_soc, pround(2))

    ambient_temperature = pb_field(pb.temp_ambient, pround(2))
    ambient_humidity = pb_field(pb.humi_ambient, pround(2))
    operating_mode = pb_field(pb.wave_operating_mode, OperatingMode.from_value)

    condensate_water_level = pb_field(pb.condensate_water_level)
    cell_temperature = pb_field(pb.bms_max_cell_temp)

    _temp_unit = pb_field(pb.user_temp_unit, TemperatureUnit.from_mode)

    battery_charge_limit_min = pb_field(pb.cms_min_dsg_soc)
    battery_charge_limit_max = pb_field(pb.cms_max_chg_soc)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet):
        processed = False

        if packet.src == 0x42 and packet.cmdSet == 0xFE and packet.cmdId == 0x15:
            self.update_from_bytes(
                ac517_apl_comm_pb2.DisplayPropertyUpload, packet.payload
            )
            processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def _send_config_packet(self, message: ac517_apl_comm_pb2.ConfigWrite):
        payload = message.SerializeToString()
        packet = Packet(0x20, 0x14, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

    async def set_battery_charge_limit_min(self, limit: int):
        if (
            self.battery_charge_limit_max is not None
            and limit > self.battery_charge_limit_max
        ):
            return False

        await self._send_config_packet(
            ac517_apl_comm_pb2.ConfigWrite(cfg_min_dsg_soc=limit)
        )
        return True

    async def set_battery_charge_limit_max(self, limit: int):
        if (
            self.battery_charge_limit_min is not None
            and limit < self.battery_charge_limit_min
        ):
            return False

        await self._send_config_packet(
            ac517_apl_comm_pb2.ConfigWrite(cfg_max_chg_soc=limit)
        )
        return True

import logging
from enum import IntEnum

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from google.protobuf.message import Message

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import mr521_pb2
from ..props import (
    Field,
    ProtobufProps,
    pb_field,
    proto_attr_mapper,
)

_LOGGER = logging.getLogger(__name__)


def _out_power(x) -> float:
    return -round(x, 2) if x != 0 else 0


def _flow_is_on(x):
    # this is the same check as in app, no idea what values other than 0 (off) or 2 (on)
    # actually represent
    return (int(x) & 0b11) in [0b10, 0b11]


pb = proto_attr_mapper(mr521_pb2.DisplayPropertyUpload)


class DCPortState(IntEnum):
    UNKNOWN = -1
    OFF = 0
    CAR = 1
    SOLAR = 2
    DC_CHARGING = 3

    @classmethod
    def from_value(cls, value: int):
        try:
            return cls(value)
        except ValueError:
            logging.debug("Encountered invalid value %s for DCPortState", value)
            return cls.UNKNOWN

    @property
    def state_name(self):
        return self.name.lower()


class Device(DeviceBase, ProtobufProps):
    """Delta Pro 3"""

    SN_PREFIX = (b"MR51",)
    NAME_PREFIX = "EF-DP3"

    battery_level = pb_field(pb.cms_batt_soc, lambda value: round(value, 2))
    battery_level_main = pb_field(pb.bms_batt_soc, lambda value: round(value, 2))

    ac_input_power = pb_field(pb.pow_get_ac, _out_power)
    ac_lv_output_power = pb_field(pb.pow_get_ac_lv_out, _out_power)
    ac_hv_output_power = pb_field(pb.pow_get_ac_hv_out, _out_power)

    input_power = pb_field(pb.pow_in_sum_w)
    output_power = pb_field(pb.pow_out_sum_w)

    dc12v_output_power = pb_field(pb.pow_get_12v, _out_power)

    dc_lv_input_power = pb_field(pb.pow_get_pv_l)
    dc_hv_input_power = pb_field(pb.pow_get_pv_h)
    dc_lv_input_state = pb_field(
        pb.plug_in_info_pv_l_type, lambda v: DCPortState.from_value(v).state_name
    )
    dc_hv_input_state = pb_field(
        pb.plug_in_info_pv_h_type, lambda v: DCPortState.from_value(v).state_name
    )

    usbc_output_power = pb_field(pb.pow_get_typec1, _out_power)
    usbc2_output_power = pb_field(pb.pow_get_typec2, _out_power)
    usba_output_power = pb_field(pb.pow_get_qcusb1, _out_power)
    usba2_output_power = pb_field(pb.pow_get_qcusb2, _out_power)

    ac_charging_speed = pb_field(pb.plug_in_info_ac_in_chg_pow_max)
    max_ac_charging_power = pb_field(pb.plug_in_info_ac_in_chg_hal_pow_max)

    plugged_in_ac = pb_field(pb.plug_in_info_ac_charger_flag)
    energy_backup = pb_field(pb.energy_backup_en)
    energy_backup_battery_level = pb_field(pb.energy_backup_start_soc)

    battery_charge_limit_min = pb_field(pb.cms_min_dsg_soc)
    battery_charge_limit_max = pb_field(pb.cms_max_chg_soc)

    cell_temperature = pb_field(pb.bms_max_cell_temp)

    dc_12v_port = pb_field(pb.flow_info_12v, _flow_is_on)
    ac_lv_port = pb_field(pb.flow_info_ac_lv_out, _flow_is_on)
    ac_hv_port = pb_field(pb.flow_info_ac_hv_out, _flow_is_on)

    solar_lv_power = Field[float]()
    solar_hv_power = Field[float]()

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet):
        processed = False

        if packet.src == 0x02 and packet.cmdSet == 0xFE and packet.cmdId == 0x15:
            _LOGGER.debug("%s: %s: Parsed data: %r", self.address, self.name, packet)
            self.update_from_bytes(mr521_pb2.DisplayPropertyUpload, packet.payload)

            processed = True
        elif (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            # Device requested for time and timezone offset, so responding with that
            # otherwise it will not be able to send us predictions and config data
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        self.solar_lv_power = self._get_solar_power(
            self.dc_lv_input_power, self.dc_lv_input_state
        )
        self.solar_hv_power = self._get_solar_power(
            self.dc_hv_input_power, self.dc_hv_input_state
        )

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    def _get_solar_power(self, power: float | None, state: str | None):
        return (
            round(power, 2)
            if state == DCPortState.SOLAR.state_name and power is not None
            else 0
        )

    async def _send_config_packet(self, message: Message):
        payload = message.SerializeToString()
        packet = Packet(0x20, 0x02, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

    async def set_energy_backup_battery_level(self, value: int):
        config = mr521_pb2.ConfigWrite()
        config.cfg_energy_backup.energy_backup_en = True
        config.cfg_energy_backup.energy_backup_start_soc = value
        await self._send_config_packet(config)
        return True

    async def enable_energy_backup(self, enabled: bool):
        config = mr521_pb2.ConfigWrite()
        config.cfg_energy_backup.energy_backup_en = enabled
        if enabled and self.energy_backup_battery_level is not None:
            config.cfg_energy_backup.energy_backup_start_soc = (
                self.energy_backup_battery_level
            )
        await self._send_config_packet(config)

    async def enable_dc_12v_port(self, enabled: bool):
        await self._send_config_packet(
            mr521_pb2.ConfigWrite(cfg_dc_12v_out_open=enabled)
        )

    async def enable_ac_hv_port(self, enabled: bool):
        await self._send_config_packet(
            mr521_pb2.ConfigWrite(cfg_hv_ac_out_open=enabled)
        )

    async def enable_ac_lv_port(self, enabled: bool):
        await self._send_config_packet(
            mr521_pb2.ConfigWrite(cfg_lv_ac_out_open=enabled)
        )

    async def set_battery_charge_limit_min(self, limit: int):
        if (
            self.battery_charge_limit_max is not None
            and limit > self.battery_charge_limit_max
        ):
            return False

        await self._send_config_packet(mr521_pb2.ConfigWrite(cfg_min_dsg_soc=limit))
        return True

    async def set_battery_charge_limit_max(self, limit: int):
        if (
            self.battery_charge_limit_min is not None
            and limit < self.battery_charge_limit_min
        ):
            return False

        await self._send_config_packet(mr521_pb2.ConfigWrite(cfg_max_chg_soc=limit))
        return True

    async def set_ac_charging_speed(self, value: int):
        if (
            self.max_ac_charging_power is None
            or value > self.max_ac_charging_power
            or value < 0
        ):
            return False

        await self._send_config_packet(
            mr521_pb2.ConfigWrite(cfg_plug_in_info_ac_in_chg_pow_max=value)
        )
        return True

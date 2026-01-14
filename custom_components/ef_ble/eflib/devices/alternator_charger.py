import logging
from math import floor

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import dc009_apl_comm_pb2
from ..props import Field, ProtobufProps, pb_field, proto_attr_mapper
from ..props.enums import IntFieldValue

pb = proto_attr_mapper(dc009_apl_comm_pb2.DisplayPropertyUpload)

_LOGGER = logging.getLogger(__name__)


class ChargerMode(IntFieldValue):
    UNKNOWN = -1

    IDLE = 0
    CHARGE = 1  # original name: DRIVING_CHARGE
    BATTERY_MAINTENANCE = 2
    REVERSE_CHARGE = 3  # original name: PARKING_CHARGE

    @classmethod
    def from_mode(cls, mode: dc009_apl_comm_pb2.SP_CHARGER_CHG_MODE):
        try:
            return cls(mode)
        except ValueError:
            _LOGGER.debug("Encountered invalid value %s for %s", mode, cls.__name__)
            return ChargerMode.UNKNOWN

    def as_pb_enum(self):
        return {
            ChargerMode.IDLE: dc009_apl_comm_pb2.SP_CHARGER_CHG_MODE_IDLE,
            ChargerMode.CHARGE: dc009_apl_comm_pb2.SP_CHARGER_CHG_MODE_DRIVING_CHG,
            ChargerMode.BATTERY_MAINTENANCE: (
                dc009_apl_comm_pb2.SP_CHARGER_CHG_MODE_BAT_MAINTENANCE
            ),
            ChargerMode.REVERSE_CHARGE: (
                dc009_apl_comm_pb2.SP_CHARGER_CHG_MODE_PARKING_CHG
            ),
        }[self]


class Device(DeviceBase, ProtobufProps):
    """Smart Generator"""

    SN_PREFIX = (b"F371", b"F372", b"DC01")
    NAME_PREFIX = "EF-F3"

    battery_level = pb_field(pb.cms_batt_soc)
    battery_temperature = pb_field(pb.cms_batt_temp)
    dc_power = pb_field(pb.pow_get_dc_bidi)

    car_battery_voltage = pb_field(pb.sp_charger_car_batt_vol, lambda x: round(x, 2))
    start_voltage = pb_field(
        pb.sp_charger_car_batt_vol_setting, lambda x: round(x / 10, 1)
    )
    start_voltage_min = Field[int]()
    start_voltage_max = Field[int]()

    charger_mode = pb_field(pb.sp_charger_chg_mode, ChargerMode.from_mode)

    charger_open = pb_field(pb.sp_charger_chg_open)
    power_limit = pb_field(pb.sp_charger_chg_pow_limit)
    power_max = pb_field(pb.sp_charger_chg_pow_max)

    reverse_charging_current_limit = pb_field(pb.sp_charger_car_batt_chg_amp_limit)
    charging_current_limit = pb_field(pb.sp_charger_dev_batt_chg_amp_limit)

    reverse_charging_current_max = pb_field(pb.sp_charger_car_batt_chg_amp_max)
    charging_current_max = pb_field(pb.sp_charger_dev_batt_chg_amp_max)

    emergency_reverse_charging = pb_field(pb.sp_charger_car_batt_urgent_chg_switch)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(device=self)
        self.start_voltage_min = 11
        self.start_voltage_max = 31

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self):
        model = ""
        match self._sn[:4]:
            case b"F371" | b"F372":
                model = "(800W)"
            case b"DC01":
                model = "(500W)"

        return f"Alternator Charger {model}".strip()

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet):
        processed = False

        if packet.src == 0x14 and packet.cmdSet == 0xFE and packet.cmdId == 0x15:
            self.update_from_bytes(
                dc009_apl_comm_pb2.DisplayPropertyUpload, packet.payload
            )
            processed = True
        elif (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def _send_config_packet(self, message: dc009_apl_comm_pb2.ConfigWrite):
        payload = message.SerializeToString()
        packet = Packet(0x20, 0x14, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

    async def enable_charger_open(self, enable: bool):
        await self._send_config_packet(
            dc009_apl_comm_pb2.ConfigWrite(cfg_sp_charger_chg_open=enable)
        )

    async def set_charger_mode(self, mode: ChargerMode):
        await self._send_config_packet(
            dc009_apl_comm_pb2.ConfigWrite(cfg_sp_charger_chg_mode=mode.as_pb_enum())
        )

    async def set_power_limit(self, limit: int):
        if self.power_max is None or limit < 0 or limit > self.power_max:
            return False

        await self._send_config_packet(
            dc009_apl_comm_pb2.ConfigWrite(cfg_sp_charger_chg_pow_limit=limit)
        )
        return True

    async def set_battery_voltage(self, value: float):
        if (
            self.start_voltage_min is None
            or self.start_voltage_max is None
            or not (self.start_voltage_min <= value <= self.start_voltage_max)
        ):
            return False

        await self._send_config_packet(
            dc009_apl_comm_pb2.ConfigWrite(
                cfg_sp_charger_car_batt_vol_setting=floor(value * 10)
            )
        )
        return True

    async def set_car_battery_curent_charge_limit(self, value: float):
        if (
            self.reverse_charging_current_max is None
            or 0 > value > self.reverse_charging_current_max
        ):
            return False
        await self._send_config_packet(
            dc009_apl_comm_pb2.ConfigWrite(cfg_sp_charger_car_batt_chg_amp_limit=value)
        )
        return True

    async def set_device_battery_current_charge_limit(self, value: float):
        if self.charging_current_max is None or 0 > value > self.charging_current_max:
            return False

        await self._send_config_packet(
            dc009_apl_comm_pb2.ConfigWrite(cfg_sp_charger_dev_batt_chg_amp_limit=value)
        )
        return True

    async def enable_emergency_reverse_charging(self, enabled: bool):
        await self._send_config_packet(
            dc009_apl_comm_pb2.ConfigWrite(
                cfg_sp_charger_car_batt_urgent_chg_switch=enabled
            )
        )

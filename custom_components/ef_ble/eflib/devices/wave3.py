import logging

from ..devicebase import DeviceBase
from ..entity import controls
from ..entity.controls import HvacMode
from ..packet import Packet
from ..pb import ac517_apl_comm_pb2
from ..props import ProtobufProps, computed_field, pb_field
from ..props.enums import IntFieldValue
from ..props.protobuf_field import proto_attr_mapper
from ..props.transforms import pround

pb_disp = proto_attr_mapper(ac517_apl_comm_pb2.DisplayPropertyUpload)
pb_mode = proto_attr_mapper(ac517_apl_comm_pb2.WaveOperatingModeParamItem)

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


class FanSpeed(IntFieldValue):
    UNKNOWN = -1

    LOW = 20
    MEDIUM_LOW = 40
    MEDIUM = 60
    MEDIUM_HIGH = 80
    HIGH = 100


class SubMode(IntFieldValue):
    UNKNOWN = -1

    NONE = 0
    NORMAL = 1
    MAX = 2
    SLEEP = 3
    ECO = 4


class TemperatureDisplayType(IntFieldValue):
    UNKNOWN = -1

    AMBIENT = 0
    SUPPLY_AIR = 1


class SleepState(IntFieldValue):
    UNKNOWN = -1

    ON = 0
    STANDBY = 1


class Device(DeviceBase, ProtobufProps):
    """Wave 3"""

    SN_PREFIX = (b"AC71",)
    NAME_PREFIX = "EF-AC"

    battery_level = pb_field(pb_disp.cms_batt_soc, pround(2))
    ambient_temperature = pb_field(pb_disp.temp_ambient, pround(2))
    ambient_humidity = pb_field(pb_disp.humi_ambient, pround(2))
    operating_mode = pb_field(pb_disp.wave_operating_mode, OperatingMode.from_value)
    condensate_water_level = pb_field(pb_disp.condensate_water_level)
    cell_temperature = pb_field(pb_disp.bms_max_cell_temp)

    pcs_fan_level = pb_field(pb_disp.pcs_fan_level)
    in_drainage = pb_field(pb_disp.in_drainage)
    drainage_mode = pb_field(pb_disp.drainage_mode)

    input_power = pb_field(pb_disp.pow_in_sum_w, pround(1))
    output_power = pb_field(pb_disp.pow_out_sum_w, pround(1))
    ac_input_power = pb_field(pb_disp.pow_get_ac, pround(1))
    battery_power = pb_field(pb_disp.pow_get_bms, pround(1))

    temp_indoor_supply_air = pb_field(pb_disp.temp_indoor_supply_air, pround(1))
    temp_unit = pb_field(pb_disp.user_temp_unit, TemperatureUnit.from_mode)

    en_pet_care = pb_field(pb_disp.en_pet_care)
    pet_care_warning = pb_field(pb_disp.pet_care_warning)

    battery_charge_limit_min = pb_field(pb_disp.cms_min_dsg_soc)
    battery_charge_limit_max = pb_field(pb_disp.cms_max_chg_soc)
    sleep_state = pb_field(pb_disp.dev_sleep_state, SleepState.from_value)
    power = pb_field(pb_disp.dev_sleep_state, lambda x: x == SleepState.ON)

    _wave_mode_info = pb_field(pb_disp.wave_mode_info)
    target_temperature_climate = pb_field(pb_mode.temp_set, pround(1))
    fan_speed_climate = pb_field(pb_mode.airflow_speed, FanSpeed.from_value)
    operating_submode = pb_field(pb_mode.submode, SubMode.from_value)

    target_humidity_climate = pb_field(pb_mode.humi_set, pround(0))
    target_temp_thermostatic_upper = pb_field(
        pb_mode.temp_thermostatic_upper_limit, pround(1)
    )
    target_temp_thermostatic_lower = pb_field(
        pb_mode.temp_thermostatic_lower_limit, pround(1)
    )

    @computed_field
    def is_submode_available(self) -> bool:
        return self.operating_mode in (OperatingMode.COOLING, OperatingMode.HEATING)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet):
        processed = False
        self.reset_updated()

        if packet.src == 0x42 and packet.cmdSet == 0xFE and packet.cmdId == 0x15:
            self.update_from_bytes(
                ac517_apl_comm_pb2.DisplayPropertyUpload, packet.payload
            )
            processed = True

        if packet.src == 0x42 and packet.cmdSet == 0xFE and packet.cmdId == 0x16:
            self.update_from_bytes(
                ac517_apl_comm_pb2.RuntimePropertyUpload, packet.payload
            )
            processed = True

        if (mode_item := self._current_mode_item) is not None:
            self.target_temperature_climate = mode_item
            self.fan_speed_climate = mode_item
            self.operating_submode = mode_item
            self.target_humidity_climate = mode_item
            self.target_temp_thermostatic_upper = mode_item
            self.target_temp_thermostatic_lower = mode_item

        self._notify_updated()
        return processed

    async def _send_config_packet(self, message: ac517_apl_comm_pb2.ConfigWrite):
        payload = message.SerializeToString()
        packet = Packet(0x20, 0x42, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
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

    _climate = controls.climate(
        operating_mode,
        translation_key="climate",
        hvac_modes={
            HvacMode.COOL: OperatingMode.COOLING,
            HvacMode.HEAT: OperatingMode.HEATING,
            HvacMode.FAN_ONLY: OperatingMode.VENTING,
            HvacMode.DRY: OperatingMode.DEHUMIDIFYING,
            HvacMode.HEAT_COOL: OperatingMode.THERMOSTATIC,
        },
        fan_modes={
            "low": FanSpeed.LOW,
            "medium_low": FanSpeed.MEDIUM_LOW,
            "medium": FanSpeed.MEDIUM,
            "medium_high": FanSpeed.MEDIUM_HIGH,
            "high": FanSpeed.HIGH,
        },
        current_temperature_field=ambient_temperature,
    )

    @_climate.power(power)
    async def enable_power(self, enabled: bool):
        cfg = ac517_apl_comm_pb2.ConfigWrite()
        if enabled:
            cfg.cfg_power_on = True
        else:
            cfg.cfg_power_off = True
        await self._send_config_packet(cfg)

    @_climate.mode()
    async def set_operating_mode(self, mode: OperatingMode):
        await self._send_config_packet(
            ac517_apl_comm_pb2.ConfigWrite(cfg_wave_operating_mode=mode.value)
        )

    @_climate.target_temp(
        target_temperature_climate,
        modes={HvacMode.COOL, HvacMode.HEAT},
        step=0.5,
        min=16,
        max=30,
    )
    async def set_target_temperature(self, temperature: float):
        await self._send_config_packet(
            ac517_apl_comm_pb2.ConfigWrite(cfg_temp_set=temperature)
        )

    @_climate.target_temp_range(
        target_temp_thermostatic_lower,
        target_temp_thermostatic_upper,
        modes={HvacMode.HEAT_COOL},
        step=0.5,
        min=16,
        max=30,
    )
    async def set_target_temperature_range(self, low: float, high: float):
        await self._send_config_packet(
            ac517_apl_comm_pb2.ConfigWrite(
                cfg_temp_thermostatic_lower_limit=low,
                cfg_temp_thermostatic_upper_limit=high,
            )
        )

    @_climate.humidity(
        target_humidity_climate,
        min=40,
        max=80,
        modes={HvacMode.DRY},
    )
    async def set_target_humidity(self, humidity: int):
        await self._send_config_packet(
            ac517_apl_comm_pb2.ConfigWrite(cfg_humi_set=float(humidity))
        )

    @_climate.fan(
        fan_speed_climate,
        modes={HvacMode.COOL, HvacMode.HEAT, HvacMode.FAN_ONLY, HvacMode.DRY},
    )
    async def set_fan_speed(self, speed: FanSpeed):
        await self._send_config_packet(
            ac517_apl_comm_pb2.ConfigWrite(cfg_airflow_speed=speed.value)
        )

    @controls.switch(en_pet_care)
    async def enable_en_pet_care(self, enabled: bool):
        await self._send_config_packet(
            ac517_apl_comm_pb2.ConfigWrite(cfg_en_pet_care=enabled)
        )

    @controls.select(
        operating_submode, options=SubMode, availability=is_submode_available
    )
    async def set_operating_submode(self, submode: SubMode):
        await self._send_config_packet(
            ac517_apl_comm_pb2.ConfigWrite(cfg_wave_operating_submode=submode.value)
        )

    @property
    def _current_mode_item(self):
        if (
            self._wave_mode_info is None
            or self.operating_mode is None
            or self.operating_mode == OperatingMode.NULL
        ):
            return None

        items = self._wave_mode_info.list_info
        if not items:
            return None

        # The list may contain 5 entries (modes 1-5) or 6 (modes 0-5 with NULL
        # placeholder at index 0)
        idx = self.operating_mode if len(items) > 5 else self.operating_mode - 1
        if 0 <= idx < len(items):
            return items[idx]

        self._logger.debug(
            "mode_index %d out of range (list length %d, mode %s)",
            idx,
            len(items),
            self.operating_mode,
        )
        return None

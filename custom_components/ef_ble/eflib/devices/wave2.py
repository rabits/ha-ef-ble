from ..devicebase import DeviceBase
from ..entity import controls, units
from ..entity.base import dynamic
from ..entity.controls import HvacMode
from ..model.kt210_sac import KT210SAC
from ..packet import Packet
from ..props import computed_field
from ..props.enums import IntFieldValue
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps
from ..props.transforms import pround

pb = dataclass_attr_mapper(KT210SAC)


class FanGear(IntFieldValue):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


class MainMode(IntFieldValue):
    COLD = 0
    WARM = 1
    FAN = 2


class SubMode(IntFieldValue):
    MAX = 0
    NIGHT = 1
    ECO = 2
    NORMAL = 3


class PowerMode(IntFieldValue):
    INIT = 0
    ON = 1
    STANDBY = 2
    OFF = 3


class WaterLevel(IntFieldValue):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


class DrainMode(IntFieldValue):
    EXTERNAL = 0
    DRAIN_FREE = 1

    @classmethod
    def from_wte(cls, value: int) -> "DrainMode":
        # bit 0 of wte_fth_en encodes the user's drain-mode preference;
        # bit 1 encodes the auto-drain master switch (handled separately).
        return cls.DRAIN_FREE if value & 1 else cls.EXTERNAL


class Device(DeviceBase, RawDataProps):
    """Wave 2"""

    SN_PREFIX = b"KT21"
    NAME_PREFIX = "EF-KT2"

    @property
    def packet_version(self):
        return 2

    battery_level = raw_field(pb.bat_soc)

    ambient_temperature = raw_field(pb.env_temp, pround(2))
    outlet_temperature = raw_field(pb.outlet_temp, pround(2))

    main_mode = raw_field(pb.mode, MainMode.from_value)
    sub_mode = raw_field(pb.sub_mode, SubMode.from_value)
    fan_speed = raw_field(pb.fan_value, FanGear.from_value)

    power_battery = raw_field(pb.bat_pwr_watt)
    power_psdr = raw_field(pb.psdr_pwr_watt)
    power_mppt = raw_field(pb.mptt_pwr_watt)

    wte_fth_en = raw_field(pb.wte_fth_en)
    water_level = raw_field(pb.water_value, WaterLevel.from_value)

    ambient_light = raw_field(pb.rgb_state, lambda x: x == 0x01)

    target_temperature = raw_field(pb.set_temp)
    power_mode = raw_field(pb.power_mode, PowerMode.from_value)
    power = raw_field(pb.power_mode, lambda x: PowerMode.from_value(x) is PowerMode.ON)
    _temp_sys = raw_field(pb.temp_sys)

    @computed_field
    def temp_unit(self) -> units.Temperature:
        return units.Temperature.F if self._temp_sys == 1 else units.Temperature.C

    @computed_field
    def target_temperature_min(self) -> int:
        return {
            units.Temperature.F: 60,
            units.Temperature.C: 16,
        }.get(self.temp_unit, 16)

    @computed_field
    def target_temperature_max(self) -> int:
        return {
            units.Temperature.F: 86,
            units.Temperature.C: 30,
        }.get(self.temp_unit, 30)

    @computed_field
    def automatic_drain(self) -> bool | None:
        if self.wte_fth_en is None:
            return None
        if self.main_mode in (MainMode.WARM, MainMode.FAN):
            return self.wte_fth_en == 1
        return self.wte_fth_en & 0b10 == 0

    @computed_field
    def drain_mode(self) -> DrainMode | None:
        if self.wte_fth_en is None:
            return None
        if self.main_mode in (MainMode.WARM, MainMode.FAN):
            return DrainMode.EXTERNAL
        return DrainMode.from_wte(self.wte_fth_en)

    # power_src looks like a bitmask, observations:
    # bit 0 - battery
    # bits 1-2 - optional internal power sources?
    # Bits 3, 5–7 - unused
    # bit 4 - AC mains
    # power_src = raw_field(pb.power_src)

    @classmethod
    def check(cls, sn):
        return sn.startswith(cls.SN_PREFIX)

    async def packet_parse(self, data: bytes):
        return Packet.from_bytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        self.reset_updated()

        if packet.src == 0x42 and packet.cmd_set == 0x42 and packet.cmd_id == 0x50:
            self.update_from_bytes(KT210SAC, packet.payload)
            processed = True

        self._notify_updated()
        return processed

    async def _send_config_packet(self, cmd_id: int, payload: bytes):
        packet = Packet(
            src=0x21,
            dst=0x42,
            cmd_set=0x42,
            cmd_id=cmd_id,
            payload=payload,
            version=self.packet_version,
        )

        await self._conn.sendPacket(packet)

    @computed_field
    def _climate_main_mode(self) -> MainMode | None:
        return self.main_mode

    _climate = controls.climate(
        _climate_main_mode,
        translation_key="climate",
        hvac_modes={
            HvacMode.COOL: MainMode.COLD,
            HvacMode.HEAT: MainMode.WARM,
            HvacMode.FAN_ONLY: MainMode.FAN,
        },
        fan_modes={
            "low": FanGear.LOW,
            "medium": FanGear.MEDIUM,
            "high": FanGear.HIGH,
        },
        current_temperature_field=ambient_temperature,
    )

    @_climate.power(power)
    async def enable_power(self, enabled: bool):
        await self.set_power_mode(PowerMode.ON if enabled else PowerMode.STANDBY)

    @controls.switch(ambient_light)
    async def enable_ambient_light(self, enabled: bool):
        await self._send_config_packet(0x5C, (0x01 if enabled else 0x02).to_bytes())

    @controls.switch(automatic_drain)
    async def enable_automatic_drain(self, enabled: bool):
        preference = (self.wte_fth_en or 0) & 1
        if not enabled:
            payload = 0b10 | preference
        elif self.main_mode in (MainMode.WARM, MainMode.FAN):
            # drain-free is unsupported outside Cool mode; the app always sends 1 (auto
            # drain on, external drainage) here
            payload = 1
        else:
            payload = preference
        await self._send_config_packet(0x59, payload.to_bytes())

    @controls.select(drain_mode, options=DrainMode)
    async def set_drain_mode(self, mode: DrainMode):
        main_mode = self.main_mode
        if main_mode is MainMode.WARM or main_mode is MainMode.FAN:
            if mode is DrainMode.DRAIN_FREE:
                self._logger.warning(
                    "Drain-free mode is not supported in %s mode, ignoring",
                    main_mode.state_name,
                )
            return
        payload = mode.value if self.automatic_drain else 0b10 | mode.value
        await self._send_config_packet(0x59, payload.to_bytes())

    @_climate.fan(
        fan_speed,
        modes={HvacMode.COOL, HvacMode.HEAT, HvacMode.FAN_ONLY},
    )
    @controls.select(fan_speed, options=FanGear)
    async def set_fan_speed(self, fan_gear: FanGear):
        await self._send_config_packet(0x5E, fan_gear.to_bytes())

    @_climate.mode()
    @controls.select(main_mode, options=MainMode)
    async def set_main_mode(self, mode: MainMode):
        await self._send_config_packet(0x51, mode.to_bytes())

    @controls.select(power_mode, options=PowerMode, exclude=[PowerMode.INIT])
    async def set_power_mode(self, mode: PowerMode):
        await self._send_config_packet(0x5B, mode.to_bytes())

    @_climate.target_temp(
        target_temperature,
        modes={HvacMode.COOL, HvacMode.HEAT},
        step=1,
        min=dynamic(target_temperature_min),
        max=dynamic(target_temperature_max),
        unit=dynamic(temp_unit),
    )
    @controls.temperature(
        target_temperature,
        min=dynamic(target_temperature_min),
        max=dynamic(target_temperature_max),
        unit=dynamic(temp_unit),
    )
    async def set_temperature(self, temperature: float):
        await self._send_config_packet(0x58, int(temperature).to_bytes())
        return True

    @controls.select(sub_mode, options=SubMode)
    async def set_sub_mode(self, sub_mode: SubMode):
        await self._send_config_packet(0x52, sub_mode.to_bytes())

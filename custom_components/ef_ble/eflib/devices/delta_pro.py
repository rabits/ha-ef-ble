from asyncio import Lock
from functools import cached_property

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..device_options import (
    UNLOCK_AC_CHARGING_MINIMUM,
    UNLOCK_DC_CHARGING_MINIMUM,
    option_field,
)
from ..devicebase import DeviceBase
from ..entity import controls
from ..entity.base import dynamic
from ..model import (
    AllKitDetailData,
    DirectBmsMDeltaHeartbeatPack,
    DirectEmsDeltaHeartbeatPack,
    DirectInvDeltaHeartbeatPack,
    DirectMpptHeartbeatPack,
    DirectPdHeartbeatPack,
)
from ..packet import Packet
from ..props import Field, computed_field
from ..props.enums import IntFieldValue
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps
from ..props.transforms import pdiv, pround


class _BmsHeartbeatBatteryMain(DirectBmsMDeltaHeartbeatPack):
    pass


class _BmsHeartbeatBattery1(DirectBmsMDeltaHeartbeatPack):
    pass


class _BmsHeartbeatBattery2(DirectBmsMDeltaHeartbeatPack):
    pass


# `num` names the pack: 0 is the main pack, 1-2 the extra batteries
_BMS_HEARTBEAT_BY_SLOT = {
    0: _BmsHeartbeatBatteryMain,
    1: _BmsHeartbeatBattery1,
    2: _BmsHeartbeatBattery2,
}

rd_pd = dataclass_attr_mapper(DirectPdHeartbeatPack)
rd_bms = dataclass_attr_mapper(_BmsHeartbeatBatteryMain)
rd_bms_1 = dataclass_attr_mapper(_BmsHeartbeatBattery1)
rd_bms_2 = dataclass_attr_mapper(_BmsHeartbeatBattery2)
rd_ems = dataclass_attr_mapper(DirectEmsDeltaHeartbeatPack)
rd_inv = dataclass_attr_mapper(DirectInvDeltaHeartbeatPack)
rd_mppt = dataclass_attr_mapper(DirectMpptHeartbeatPack)
rd_kit = dataclass_attr_mapper(AllKitDetailData)


class ScreenTimeout(IntFieldValue):
    """Seconds until the screen turns off"""

    UNKNOWN = -1

    NEVER = 0
    SEC_10 = 10
    SEC_30 = 30
    MIN_1 = 60
    MIN_5 = 300
    MIN_30 = 1800


class UnitTimeout(IntFieldValue):
    """Minutes without a load until the unit turns off"""

    UNKNOWN = -1

    NEVER = 0
    MIN_30 = 30
    HOUR_1 = 60
    HOUR_2 = 120
    HOUR_6 = 360
    HOUR_12 = 720


class Device(DeviceBase, RawDataProps):
    """Delta Pro"""

    SN_PREFIX = (
        b"DCA",
        b"DCK",
        b"DCE",
        b"DCC",
        b"DCU",
        b"DCT",
        b"DCG",
        b"DCS",
        b"DCF",
        b"DCJ",
        b"Z1",
        b"R511",
    )
    NAME_PREFIX = "EF-DC"

    @property
    def packet_version(self) -> int:
        return 0x02

    @property
    def auth_header_dst(self) -> int:
        return 0x32

    battery_level = raw_field(rd_ems.f32_lcd_show_soc, pround(2))
    battery_charge_limit_min = raw_field(rd_ems.min_dsg_soc)
    battery_charge_limit_max = raw_field(rd_ems.max_charge_soc)
    remaining_time_charging = raw_field(rd_ems.chg_remain_time)
    remaining_time_discharging = raw_field(rd_ems.dsg_remain_time)

    battery_level_main = raw_field(rd_bms.f32_show_soc, pround(2))
    battery_voltage = raw_field(rd_bms.vol, pdiv(1000, 2))
    max_cell_voltage = raw_field(rd_bms.max_cell_vol, pdiv(1000, 3))
    min_cell_voltage = raw_field(rd_bms.min_cell_vol, pdiv(1000, 3))
    battery_temperature = raw_field(rd_bms.temp)
    cell_temperature = raw_field(rd_bms.max_cell_temp)
    state_of_health = raw_field(rd_bms.soh)

    battery_1_enabled = Field[bool]()
    battery_1_battery_level = Field[float]()
    battery_1_sn = Field[str]()
    battery_1_cell_temperature = raw_field(rd_bms_1.max_cell_temp)
    battery_1_voltage = raw_field(rd_bms_1.vol, pdiv(1000, 2))
    battery_1_max_cell_voltage = raw_field(rd_bms_1.max_cell_vol, pdiv(1000, 3))
    battery_1_min_cell_voltage = raw_field(rd_bms_1.min_cell_vol, pdiv(1000, 3))
    battery_1_input_power = raw_field(rd_bms_1.input_watts)
    battery_1_output_power = raw_field(rd_bms_1.output_watts)

    battery_2_enabled = Field[bool]()
    battery_2_battery_level = Field[float]()
    battery_2_sn = Field[str]()
    battery_2_cell_temperature = raw_field(rd_bms_2.max_cell_temp)
    battery_2_voltage = raw_field(rd_bms_2.vol, pdiv(1000, 2))
    battery_2_max_cell_voltage = raw_field(rd_bms_2.max_cell_vol, pdiv(1000, 3))
    battery_2_min_cell_voltage = raw_field(rd_bms_2.min_cell_vol, pdiv(1000, 3))
    battery_2_input_power = raw_field(rd_bms_2.input_watts)
    battery_2_output_power = raw_field(rd_bms_2.output_watts)

    ac_output_power = raw_field(rd_inv.output_watts)
    ac_output_voltage = raw_field(rd_inv.inv_out_vol, pdiv(1000, 2))
    ac_input_power = raw_field(rd_inv.input_watts)
    ac_input_voltage = raw_field(rd_inv.ac_in_vol, pdiv(1000, 2))
    ac_input_current = raw_field(rd_inv.ac_in_amp, pdiv(1000, 2))
    ac_ports = raw_field(rd_inv.cfg_ac_enabled, lambda x: x == 1)
    ac_xboost = raw_field(rd_inv.cfg_ac_xboost, lambda x: x == 1)
    ac_always_on = raw_field(rd_pd.ac_auto_config, lambda x: x == 1)
    _min_ac_out_soc = raw_field(rd_pd.min_ac_out_soc)

    dc_input_power = raw_field(rd_mppt.in_watts, pdiv(10, 1))
    dc_input_voltage = raw_field(rd_mppt.in_vol, pdiv(10, 1))
    dc_input_current = raw_field(rd_mppt.in_amp, pdiv(100, 2))

    ac_charging_speed = raw_field(rd_inv.cfg_slow_chg_watts)
    ac_charging_speed_min = option_field(
        UNLOCK_AC_CHARGING_MINIMUM, enabled=1, disabled=200
    )
    _ac_chg_rated_power = raw_field(rd_inv.ac_chg_rated_power)
    _cfg_ac_out_voltage = raw_field(rd_inv.cfg_ac_out_voltage)

    @computed_field
    def ac_charging_power_max(self) -> int | None:
        if self._ac_chg_rated_power is None:
            return None
        if self._ac_chg_rated_power > 200:
            return self._ac_chg_rated_power
        # 230 V units that report a rated power report 2900 W, the cloud's limit too
        return 2900 if (self._cfg_ac_out_voltage or 0) >= 200_000 else 1800

    input_power = raw_field(rd_pd.watts_in_sum)
    output_power = raw_field(rd_pd.watts_out_sum)
    dc_output_power = raw_field(rd_mppt.car_out_watts, pdiv(10, 1))
    anderson_out_power = raw_field(rd_mppt.dcdc_12v_watts)

    dc_12v_port = raw_field(rd_mppt.car_state, lambda x: x == 1)
    dc_charging_max_amps = raw_field(rd_mppt.cfg_dc_chg_current, pdiv(1000))
    dc_charging_amps_min = option_field(
        UNLOCK_DC_CHARGING_MINIMUM, enabled=0, disabled=4
    )
    energy_backup = raw_field(rd_pd.watth_is_config, lambda x: x == 1)
    energy_backup_battery_level = raw_field(rd_pd.backup_soc)

    generator_auto_start_level = raw_field(rd_ems.open_oil_eb_soc)
    generator_auto_stop_level = raw_field(rd_ems.close_oil_eb_soc)

    # 0 turns the beeper on, 1 turns it off
    beeper = raw_field(rd_pd.beep_mode, lambda x: x == 0)
    screen_timeout = raw_field(rd_pd.lcd_off_sec, ScreenTimeout.from_value)
    unit_timeout = raw_field(rd_pd.standby_min, UnitTimeout.from_value)

    usbc_output_power = raw_field(rd_pd.typec1_watts)
    usbc2_output_power = raw_field(rd_pd.typec2_watts)
    usba_output_power = raw_field(rd_pd.usb1_watts)
    usba2_output_power = raw_field(rd_pd.usb2_watts)
    qc_usb1_output_power = raw_field(rd_pd.qc_usb1_watts)
    qc_usb2_output_power = raw_field(rd_pd.qc_usb2_watts)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._lock = Lock()

        self.index = 0
        self._dormant = True
        self._wake_up_sent = False
        self._initialized = False

        self.add_timer_task(self.request_heartbeat, 0.35)

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return (
            sn[:4] in cls.SN_PREFIX
            or sn[:3] in cls.SN_PREFIX
            or sn[:2] in cls.SN_PREFIX
        )

    async def packet_parse(self, data: bytes):
        return Packet.from_bytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet) -> bool:
        self.reset_updated()

        match packet.src, packet.cmd_set, packet.cmd_id:
            case 0x03, 0x03, 0x0E:
                async with self._lock:
                    self._initialized = True
                kit = self.update_from_bytes(AllKitDetailData, packet.payload)
                if kit is not None:
                    self._update_extra_batteries(kit)

            case 0x03, 0x32, 0x05:
                async with self._lock:
                    dormant = self._dormant

                if dormant:
                    # dormancy status
                    await self.send_packet(
                        Packet(
                            src=0x21,
                            dst=0x32,
                            cmd_set=0x33,
                            cmd_id=0x01,
                            payload=b"\x01",
                            version=self.packet_version,
                        ),
                        wait_for_response=False,
                    )

                    async with self._lock:
                        self._dormant = False
            case 0x02, 0x20, 0x02:
                self.update_from_bytes(DirectPdHeartbeatPack, packet.payload)
            case _, 0x20, 0x32:
                if not self._parse_bms_heartbeat(packet.payload):
                    return False
            case 0x03, 0x20, 0x02:
                self.update_from_bytes(DirectEmsDeltaHeartbeatPack, packet.payload)
            case 0x04, 0x20, 0x02:
                self.update_from_bytes(DirectInvDeltaHeartbeatPack, packet.payload)
            case self._mppt_dst, 0x20, 0x02:
                self.update_from_bytes(DirectMpptHeartbeatPack, packet.payload)
            case _:
                return False

        async with self._lock:
            wake_up = False
            if self._initialized and not self._wake_up_sent:
                wake_up = True

        if wake_up:
            await self.send_wake_up()

        self._notify_updated()

        return True

    async def send_wake_up(self):
        async with self._lock:
            self._wake_up_sent = True

        await self.send_packet(
            Packet(
                src=0x21,
                dst=0x03,
                cmd_set=0x32,
                cmd_id=0x05,
                payload=b"\x01",
                version=self.packet_version,
            )
        )

    async def request_heartbeat(self):
        async with self._lock:
            if self._dormant:
                return

        cmd_map = {
            0: (0x21, 0x02, 0x20, 0x02),
            1: (0x21, 0x05, 0x20, 0x02),
            2: (0x21, 0x04, 0x20, 0x02),
            3: (0x21, 0x03, 0x20, 0x02),
            4: (0x21, 0x03, 0x20, 0x32),
            # 5: (0x21, 0x05, 0x20, 0x48),
        }

        src, dst, cmd_set, cmd_id = cmd_map[self.index]
        async with self._lock:
            self.index = (self.index + 1) % len(cmd_map)

        await self.send_packet(
            Packet(
                src=src,
                dst=dst,
                cmd_set=cmd_set,
                cmd_id=cmd_id,
                payload=b"\x00",
                version=self.packet_version,
            ),
            wait_for_response=False,
        )

    def _parse_bms_heartbeat(self, payload: bytes) -> bool:
        """Route a BMS heartbeat to the pack named by `num` in its payload"""
        if not payload:
            return False

        heartbeat_type = _BMS_HEARTBEAT_BY_SLOT.get(payload[0])
        if heartbeat_type is None:
            return False

        self.update_from_bytes(heartbeat_type, payload)
        return True

    def _update_extra_batteries(self, kit_data: AllKitDetailData):
        battery_entity_map = [
            {
                "enabled": Device.battery_1_enabled,
                "sn": Device.battery_1_sn,
                "level": Device.battery_1_battery_level,
            },
            {
                "enabled": Device.battery_2_enabled,
                "sn": Device.battery_2_sn,
                "level": Device.battery_2_battery_level,
            },
        ]
        for i, kit in enumerate(kit_data.kit_base_info):
            battery_dict = battery_entity_map[i]
            available = kit.avai_flag
            self.set_value(battery_dict["enabled"], bool(available))
            if available:
                self.set_value(battery_dict["sn"], kit.sn.strip(b"\x00").decode())
                self.set_value(battery_dict["level"], round(kit.f32_soc, 2))

    @cached_property
    def _mppt_dst(self) -> int:
        return 0x07 if self._sn.startswith("R511") else 0x05

    async def _send_config_packet(self, dst: int, cmd_id: int, payload: bytes):
        await self.send_packet(
            Packet(0x21, dst, 0x20, cmd_id, payload, version=0x02),
            raise_on_failure=True,
        )

    @controls.outlet(ac_ports)
    async def enable_ac_ports(self, enabled: bool):
        payload = bytes([1 if enabled else 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        await self._send_config_packet(0x04, 0x42, payload)

    @controls.switch(ac_xboost)
    async def enable_ac_xboost(self, enabled: bool):
        payload = bytes([0xFF, 1 if enabled else 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        await self._send_config_packet(0x04, 0x42, payload)

    @controls.switch(ac_always_on)
    async def enable_ac_always_on(self, enabled: bool):
        # The command also sets the minimum level, so it repeats the current one
        if self._min_ac_out_soc is None:
            self._logger.warning("AC always on not set: minimum level not known yet")
            return
        payload = bytes([1 if enabled else 0, self._min_ac_out_soc])
        await self._send_config_packet(0x02, 0x5F, payload)

    @controls.outlet(dc_12v_port)
    async def enable_dc_12v_port(self, enabled: bool):
        await self._send_config_packet(self._mppt_dst, 0x51, enabled.to_bytes())

    @controls.current(
        dc_charging_max_amps, min=dynamic(dc_charging_amps_min), max=8, step=2
    )
    async def set_dc_charging_amps_max(self, value: float):
        milliamps = int(value * 1000).to_bytes(4, "little")
        await self._send_config_packet(self._mppt_dst, 0x47, milliamps)
        return True

    @controls.battery(
        battery_charge_limit_max, min=dynamic(battery_charge_limit_min), max=100
    )
    async def set_battery_charge_limit_max(self, limit: float):
        await self._send_config_packet(0x03, 0x31, int(limit).to_bytes())
        return True

    @controls.battery(battery_charge_limit_min, max=dynamic(battery_charge_limit_max))
    async def set_battery_charge_limit_min(self, limit: float):
        await self._send_config_packet(0x03, 0x33, int(limit).to_bytes())
        return True

    @controls.power(
        ac_charging_speed,
        min=dynamic(ac_charging_speed_min),
        max=dynamic(ac_charging_power_max),
    )
    async def set_ac_charging_speed(self, value: float):
        payload = bytes([0xFF, 0xFF]) + int(value).to_bytes(2, "little") + bytes([0xFF])
        await self.send_packet(
            Packet(0x20, 0x04, 0x20, 0x45, payload, version=0x02),
            raise_on_failure=True,
        )
        return True

    @controls.switch(energy_backup)
    async def enable_energy_backup(self, enabled: bool):
        backup_level = self.energy_backup_battery_level or 50
        await self._send_backup_packet(backup_level, enabled=enabled)

    @controls.battery(
        energy_backup_battery_level,
        min=dynamic(battery_charge_limit_min),
        max=dynamic(battery_charge_limit_max),
        availability=energy_backup,
    )
    async def set_energy_backup_battery_level(self, value: float):
        await self._send_backup_packet(int(value), enabled=True)
        return True

    async def _send_backup_packet(self, value: int, *, enabled: bool):
        payload = bytes([0x01 if enabled else 0, value, 0x00, 0x00])
        await self._send_config_packet(0x02, 0x5E, payload)

    @controls.battery(generator_auto_start_level, min=0, max=30)
    async def set_generator_auto_start_level(self, value: float):
        await self._send_config_packet(0x03, 0x34, int(value).to_bytes())
        return True

    @controls.battery(generator_auto_stop_level, min=50, max=100)
    async def set_generator_auto_stop_level(self, value: float):
        await self._send_config_packet(0x03, 0x35, int(value).to_bytes())
        return True

    @controls.switch(beeper)
    async def enable_beeper(self, enabled: bool):
        await self._send_config_packet(0x02, 0x26, bytes([0 if enabled else 1]))

    @controls.select(screen_timeout, options=ScreenTimeout)
    async def set_screen_timeout(self, value: ScreenTimeout):
        payload = value.to_bytes(2, "little") + bytes([0xFF])
        await self._send_config_packet(0x02, 0x27, payload)

    @controls.select(unit_timeout, options=UnitTimeout)
    async def set_unit_timeout(self, value: UnitTimeout):
        await self._send_config_packet(0x02, 0x21, value.to_bytes(2, "little"))

    async def enable_solar_priority(self, enabled: bool):
        await self._send_config_packet(0x02, 0x5C, bytes([1 if enabled else 0]))

    async def set_screen_brightness(self, value: int):
        await self._send_config_packet(0x02, 0x27, bytes([0xFF, 0xFF, value]))

    async def set_ac_standby_time(self, minutes: int):
        await self._send_config_packet(0x04, 0x99, minutes.to_bytes(2, "little"))

    async def set_dc_standby_time(self, minutes: int):
        await self._send_config_packet(0x05, 0x54, minutes.to_bytes(2, "little"))

    async def set_dc_charging_type(self, type_id: int):
        # 0 car 1 adapter ?
        await self._send_config_packet(0x05, 0x52, bytes([type_id]))

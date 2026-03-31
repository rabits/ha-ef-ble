from enum import IntEnum
from functools import partial

from ..commands import TimeCommands
from ..devicebase import AdvertisementData, BLEDevice, DeviceBase
from ..entity import controls
from ..entity.base import dynamic
from ..packet import Packet
from ..pb import yj751_sys_pb2
from ..props import (
    Field,
    ProtobufProps,
    field_group,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)
from ..props.enums import IntFieldValue
from ..props.utils import pmultiply, prop_has_bit_off, prop_has_bit_on, pround

pb_heartbeat = proto_attr_mapper(yj751_sys_pb2.AppShowHeartbeatReport)
pb_backend_record_heartbeat = proto_attr_mapper(
    yj751_sys_pb2.BackendRecordHeartbeatReport
)
pb_bp_info = proto_attr_mapper(yj751_sys_pb2.BpInfoReport)
pb_app_para_heartbeat = proto_attr_mapper(yj751_sys_pb2.APPParaHeartbeatReport)
pb_display_property_upload = proto_attr_mapper(yj751_sys_pb2.DisplayPropertyUpload)


class OperatingMode(IntFieldValue):
    NONE = 0
    SELF_POWERED = 1
    SCHEDULED = 2
    TIME_OF_USE = 3


class Access5p8InputType(IntFieldValue):
    IN_IDLE = 0
    IN_AC_EV = 1
    IN_PD303 = 2
    IN_L14_TRANS = 3


class Access5p8OutputType(IntFieldValue):
    OUT_IDLE = 0
    OUT_PARALLEL_BOX = 1
    OUT_PD303 = 2


class SolarSource(IntEnum):
    LV = 0
    HV = 1


class _BatteryLevel(
    repeated_pb_field_type(
        list_field=pb_bp_info.bp_info, value_field=lambda x: x.bp_soc, per_item=True
    )
):
    battery_no: int

    def get_value(self, item: yj751_sys_pb2.BPInfo) -> int | None:
        return item.bp_soc if item.bp_no == self.battery_no else None


class _BatteryTemperature(
    repeated_pb_field_type(
        list_field=pb_bp_info.bp_info, value_field=lambda x: x.bp_temp, per_item=True
    )
):
    battery_no: int

    def get_value(self, item: yj751_sys_pb2.BPInfo) -> int | None:
        return item.bp_temp if item.bp_no == self.battery_no else None


def _bracket(min_val: float, value: float, max_val: float) -> int:
    return int(max(min_val, min(value, max_val)))


class Device(DeviceBase, ProtobufProps):
    """Delta Pro Ultra"""

    SN_PREFIX = b"Y711"
    NAME_PREFIX = "EF-YJ"

    # Bitmap for various binary states and the individual binary states therein
    show_flag = pb_field(pb_heartbeat.show_flag)
    is_charging = pb_field(pb_heartbeat.show_flag, prop_has_bit_on(0))
    dc_ports = pb_field(pb_heartbeat.show_flag, prop_has_bit_on(1))
    slow_charging = pb_field(pb_heartbeat.show_flag, prop_has_bit_on(4))
    ac_allowed = pb_field(pb_heartbeat.show_flag, prop_has_bit_off(9))
    ac_ports = pb_field(pb_heartbeat.show_flag, prop_has_bit_on(2))
    ac_ports_availability = pb_field(pb_heartbeat.show_flag, prop_has_bit_off(9))

    battery_level = pb_field(pb_heartbeat.soc)

    lv_solar_power = pb_field(pb_heartbeat.in_lv_mppt_pwr, pround(2))
    lv_solar_voltage = pb_field(pb_backend_record_heartbeat.in_lv_mppt_vol, pround(2))
    lv_solar_current = pb_field(pb_backend_record_heartbeat.in_lv_mppt_amp, pround(2))
    lv_solar_temperature = pb_field(pb_backend_record_heartbeat.mppt_lv_temp, pround(2))
    lv_solar_error_code = pb_field(pb_backend_record_heartbeat.lv_pv_err_code)

    hv_solar_power = pb_field(pb_heartbeat.in_hv_mppt_pwr, pround(2))
    hv_solar_voltage = pb_field(pb_backend_record_heartbeat.in_hv_mppt_vol, pround(2))
    hv_solar_current = pb_field(pb_backend_record_heartbeat.in_hv_mppt_amp, pround(2))
    hv_solar_temperature = pb_field(pb_backend_record_heartbeat.mppt_hv_temp, pround(2))
    hv_solar_error_code = pb_field(pb_backend_record_heartbeat.hv_pv_err_code)

    ac_5p8_in_power = pb_field(pb_heartbeat.in_ac_5p8_pwr, pround(2))
    ac_5p8_in_voltage = pb_field(pb_backend_record_heartbeat.in_ac_5p8_vol, pround(2))
    ac_5p8_in_current = pb_field(pb_backend_record_heartbeat.in_ac_5p8_amp, pround(2))
    ac_5p8_in_type = pb_field(
        pb_heartbeat.access_5p8_in_type, Access5p8InputType.from_value
    )

    ac_c20_in_power = pb_field(pb_heartbeat.in_ac_c20_pwr, pround(2))
    ac_c20_in_voltage = pb_field(pb_backend_record_heartbeat.in_ac_c20_vol, pround(2))
    ac_c20_in_current = pb_field(pb_backend_record_heartbeat.in_ac_c20_amp, pround(2))
    ac_c20_in_type = pb_field(pb_backend_record_heartbeat.c20_in_type)

    hv_solar_weak = pb_field(
        pb_display_property_upload.plug_in_info_pv_weak_source_flag,
        prop_has_bit_on(SolarSource.HV),
    )
    lv_solar_weak = pb_field(
        pb_display_property_upload.plug_in_info_pv_weak_source_flag,
        prop_has_bit_on(SolarSource.LV),
    )
    hv_solar_low_voltage = pb_field(
        pb_display_property_upload.plug_in_info_pv_vol_low_flag,
        prop_has_bit_on(SolarSource.HV),
    )
    lv_solar_low_voltage = pb_field(
        pb_display_property_upload.plug_in_info_pv_vol_low_flag,
        prop_has_bit_on(SolarSource.LV),
    )

    ac_in_freq = pb_field(pb_backend_record_heartbeat.ac_in_freq)
    ac_out_freq = pb_field(pb_backend_record_heartbeat.ac_out_freq)

    battery_voltage = pb_field(pb_backend_record_heartbeat.bat_vol, pround(2))
    battery_current = pb_field(pb_backend_record_heartbeat.bat_amp, pround(2))

    battery_input_power = pb_field(
        pb_backend_record_heartbeat.bms_input_watts, pround(2)
    )
    battery_output_power = pb_field(
        pb_backend_record_heartbeat.bms_output_watts, pround(2)
    )

    dc_inverter_temperature = pb_field(
        pb_backend_record_heartbeat.pcs_dc_temp, pround(2)
    )
    dc_inverter_error_code = pb_field(pb_backend_record_heartbeat.pcs_dc_err_code)
    ac_inverter_temperature = pb_field(
        pb_backend_record_heartbeat.pcs_ac_temp, pround(2)
    )
    ac_inverter_error_code = pb_field(pb_backend_record_heartbeat.pcs_ac_err_code)

    system_temperature = pb_field(pb_backend_record_heartbeat.pd_temp, pround(2))

    input_power = pb_field(pb_heartbeat.watts_in_sum)
    output_power = pb_field(pb_heartbeat.watts_out_sum)

    battery_enabled = field_group(
        lambda _: Field[bool](), 5, name_template="battery_{n}_enabled"
    )
    battery_battery_level = field_group(
        _BatteryLevel, 5, name_template="battery_{n}_battery_level"
    )
    battery_cell_temperature = field_group(
        _BatteryTemperature, 5, name_template="battery_{n}_cell_temperature"
    )

    usb1_out_power = pb_field(pb_heartbeat.out_usb1_pwr)
    usb1_out_voltage = pb_field(pb_backend_record_heartbeat.out_usb1_vol, pround(2))
    usb1_out_current = pb_field(pb_backend_record_heartbeat.out_usb1_amp, pround(2))

    usb2_out_power = pb_field(pb_heartbeat.out_usb2_pwr)
    usb2_out_voltage = pb_field(pb_backend_record_heartbeat.out_usb2_vol, pround(2))
    usb2_out_current = pb_field(pb_backend_record_heartbeat.out_usb2_amp, pround(2))

    typec1_out_power = pb_field(pb_heartbeat.out_typec1_pwr)
    typec1_out_voltage = pb_field(pb_backend_record_heartbeat.out_typec1_vol, pround(2))
    typec1_out_current = pb_field(pb_backend_record_heartbeat.out_typec1_amp, pround(2))

    typec2_out_power = pb_field(pb_heartbeat.out_typec2_pwr)
    typec2_out_voltage = pb_field(pb_backend_record_heartbeat.out_typec2_vol, pround(2))
    typec2_out_current = pb_field(pb_backend_record_heartbeat.out_typec2_amp, pround(2))

    anderson_out_power = pb_field(pb_heartbeat.out_ads_pwr)
    anderson_out_voltage = pb_field(pb_backend_record_heartbeat.out_ads_vol, pround(2))
    anderson_out_current = pb_field(pb_backend_record_heartbeat.out_ads_amp, pround(2))
    anderson_out_error_code = pb_field(pb_backend_record_heartbeat.ads_err_code)

    ac_l1_1_out_power = pb_field(pb_heartbeat.out_ac_l1_1_pwr)
    ac_l1_1_out_voltage = pb_field(
        pb_backend_record_heartbeat.out_ac_l1_1_vol, pround(2)
    )
    ac_l1_1_out_current = pb_field(
        pb_backend_record_heartbeat.out_ac_l1_1_amp, pround(2)
    )
    ac_l1_1_out_power_factor = pb_field(
        pb_backend_record_heartbeat.out_ac_l1_1_pf, pmultiply(100)
    )

    ac_l1_2_out_power = pb_field(pb_heartbeat.out_ac_l1_2_pwr)
    ac_l1_2_out_voltage = pb_field(
        pb_backend_record_heartbeat.out_ac_l1_2_vol, pround(2)
    )
    ac_l1_2_out_current = pb_field(
        pb_backend_record_heartbeat.out_ac_l1_2_amp, pround(2)
    )
    ac_l1_2_out_power_factor = pb_field(
        pb_backend_record_heartbeat.out_ac_l1_2_pf, pmultiply(100)
    )

    ac_l2_1_out_power = pb_field(pb_heartbeat.out_ac_l2_1_pwr)
    ac_l2_1_out_voltage = pb_field(
        pb_backend_record_heartbeat.out_ac_l2_1_vol, pround(2)
    )
    ac_l2_1_out_current = pb_field(
        pb_backend_record_heartbeat.out_ac_l2_1_amp, pround(2)
    )
    ac_l2_1_out_power_factor = pb_field(
        pb_backend_record_heartbeat.out_ac_l2_1_pf, pmultiply(100)
    )

    ac_l2_2_out_power = pb_field(pb_heartbeat.out_ac_l2_2_pwr)
    ac_l2_2_out_voltage = pb_field(
        pb_backend_record_heartbeat.out_ac_l2_2_vol, pround(2)
    )
    ac_l2_2_out_current = pb_field(
        pb_backend_record_heartbeat.out_ac_l2_2_amp, pround(2)
    )
    ac_l2_2_out_power_factor = pb_field(
        pb_backend_record_heartbeat.out_ac_l2_2_pf, pmultiply(100)
    )

    ac_tt_out_power = pb_field(pb_heartbeat.out_ac_tt_pwr)
    ac_tt_out_voltage = pb_field(pb_backend_record_heartbeat.out_ac_tt_vol, pround(2))
    ac_tt_out_current = pb_field(pb_backend_record_heartbeat.out_ac_tt_amp, pround(2))
    ac_tt_out_power_factor = pb_field(
        pb_backend_record_heartbeat.out_ac_tt_pf, pmultiply(100)
    )

    ac_l14_out_power = pb_field(pb_heartbeat.out_ac_l14_pwr)
    ac_l14_out_voltage = pb_field(pb_backend_record_heartbeat.out_ac_l14_vol, pround(2))
    ac_l14_out_current = pb_field(pb_backend_record_heartbeat.out_ac_l14_amp, pround(2))
    ac_l14_out_power_factor = pb_field(
        pb_backend_record_heartbeat.out_ac_l14_pf, pmultiply(100)
    )

    ac_5p8_out_type = pb_field(
        pb_heartbeat.access_5p8_out_type, Access5p8OutputType.from_value
    )
    ac_5p8_out_power = pb_field(pb_heartbeat.out_ac_5p8_pwr)
    ac_5p8_out_voltage = pb_field(pb_backend_record_heartbeat.out_ac_5p8_vol, pround(2))
    ac_5p8_out_current = pb_field(pb_backend_record_heartbeat.out_ac_5p8_amp, pround(2))
    ac_5p8_out_power_factor = pb_field(
        pb_backend_record_heartbeat.out_ac_5p8_pf, pmultiply(100)
    )

    backup_discharge_limit = pb_field(pb_app_para_heartbeat.dsg_min_soc)

    backup_charge_limit = pb_field(pb_app_para_heartbeat.chg_max_soc)

    backup_reserve_level = pb_field(pb_app_para_heartbeat.sys_backup_soc)

    operating_mode_select = pb_field(
        pb_app_para_heartbeat.sys_word_mode, OperatingMode.from_value
    )

    ac_5p8_charging_power = pb_field(pb_app_para_heartbeat.chg_5p8_set_watts)

    ac_c20_charging_power = pb_field(pb_app_para_heartbeat.chg_c20_set_watts)
    ac_c20_charging_power_availability = pb_field(
        # slow charging switch must be enabled
        pb_heartbeat.show_flag,
        prop_has_bit_on(4),
    )

    # Properties for un-implemented controls and sensors
    # wireless_4g = pb_field(pb_heartbeat.wireless_4g_on, bool)
    # power_standby_minutes = pb_field(pb_app_para_heartbeat.power_standby_mins)
    # screen_standby_seconds = pb_field(pb_app_para_heartbeat.screen_standby_sec)
    # dc_standby_minutes = pb_field(pb_app_para_heartbeat.dc_standby_mins)
    # ac_standby_minutes = pb_field(pb_app_para_heartbeat.ac_standby_mins)
    # battery_heating = pb_field(pb_app_para_heartbeat.bms_mode_set, bool)
    # solar_only = pb_field(pb_app_para_heartbeat.solar_only_flg, bool)
    # ac_xboost = pb_field(pb_app_para_heartbeat.ac_xboost, bool)
    # ac_always_on = pb_field(pb_app_para_heartbeat.ac_often_open_flg, bool)
    # ac_always_on_soc = pb_field(pb_app_para_heartbeat.ac_often_open_min_soc, int)
    # ev_max_charger_cur = pb_field(
    #     pb_backend_record_heartbeat.ev_max_charger_cur, pround(2)
    # )
    # fan_running = pb_field(pb_backend_record_heartbeat.fan_state, bool)

    extra_battery_name = "Delta Pro Ultra Battery"

    @staticmethod
    def check(sn):
        return sn.startswith(Device.SN_PREFIX)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)
        # Add timer to request heartbeat info from backend using update_period
        # with minimum 2 seconds to avoid spamming the device with requests
        self.add_timer_task(
            partial(self.request_heartbeat_info, 8),
            interval=max(2, self._update_period),
        )

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet) -> bool:
        """Process the incoming notifications from the device"""

        processed = True
        self.reset_updated()
        match (packet.src, packet.cmdSet, packet.cmdId):
            case 0x02, 0x02, 0x01:
                # Ping
                await self._conn.replyPacket(packet)
                self._logger.debug(
                    "%s: %s: Parsed data: %r", self.address, self.name, packet
                )
                self.update_from_bytes(
                    yj751_sys_pb2.AppShowHeartbeatReport, packet.payload
                )
                # self._logger.debug("DPU AppShowHeartbeatReport: \n %s", str(p))
            case 0x02, 0x02, 0x02:
                # BackendRecordHeartbeatReport
                await self._conn.replyPacket(packet)
                self.update_from_bytes(
                    yj751_sys_pb2.BackendRecordHeartbeatReport, packet.payload
                )
                # self._logger.debug("DPU BackendRecordHeartbeatReport: \n %s", str(p))
            case 0x02, 0x02, 0x03:
                await self._conn.replyPacket(packet)
                self.update_from_bytes(
                    yj751_sys_pb2.APPParaHeartbeatReport, packet.payload
                )
                # self._logger.debug("DPU APPParaHeartbeatReport: \n %s", str(p))
            case 0x02, 0x02, 0x04:
                await self._conn.replyPacket(packet)
                self.update_from_bytes(yj751_sys_pb2.BpInfoReport, packet.payload)
                # self._logger.debug("DPU BpInfoReport: \n %s", str(p))
            case 0x02, 0x0A, 0x20:
                await self._conn.replyPacket(packet)
                self.update_from_bytes(yj751_sys_pb2.CurrentNode, packet.payload)
                # self._logger.debug("DPU CurrentNode: \n %s", str(p))
            case 0x02, 0xFE, 0x15:
                await self._conn.replyPacket(packet)
                self.update_from_bytes(
                    yj751_sys_pb2.DisplayPropertyUpload, packet.payload
                )
                # self._logger.debug("DPU DisplayPropertyUpload: \n %s", str(p))
            case 0x02, 0x02, 0x17:
                await self._conn.replyPacket(packet)
                self.update_from_bytes(yj751_sys_pb2.DevRequest, packet.payload)
                # self._logger.debug("DPU DevRequest: \n %s", str(p))
            case 0x35, 0x35, 0x20:
                self._logger.debug(
                    "%s: %s: Ping received: %r", self.address, self.name, packet
                )
            case 0x35, 0x01, Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME:
                # Device requested for time and timezone offset, so responding with that
                # otherwise it will not be able to send us predictions and config data
                if len(packet.payload) == 0:
                    self._time_commands.async_send_all()
            case _:
                self._logger.debug(
                    "%s: %s: Unhandled packet: %r", self.address, self.name, packet
                )
                processed = False

        for field_name in self.updated_fields:
            try:
                self.update_callback(field_name)
                self.update_state(field_name, getattr(self, field_name))
            except Exception as e:  # noqa: BLE001
                self._logger.warning(
                    "Error happened while updating field %s: %s", field_name, e
                )

        return processed

    async def _send_command_packet(self, dst: int, cmd_func: int, cmd_id: int, message):
        payload = message.SerializeToString()
        p = Packet(0x21, dst, cmd_func, cmd_id, payload, 0x01, 0x01, 0x13)

        await self._conn.sendPacket(p)

    async def enable_wireless_4g(self, enable: bool):
        """Send command to enable/disable wireless 4G"""
        self._logger.debug("enable_wireless_4g: %s", enable)

        # Current value from pb_heartbeat.wireless_4g_on
        message = yj751_sys_pb2.Switch4GEnable(en_4G_open=int(enable))

        await self._send_command_packet(
            dst=0x35, cmd_func=0x35, cmd_id=0x75, message=message
        )
        return True

    @controls.outlet(dc_ports)
    async def enable_dc_ports(self, enable: bool):
        """Send command to enable/disable DC"""
        self._logger.debug("enable_dc_ports: %s", enable)

        # Current value from pb_heartbeat.show_flag bit 1
        message = yj751_sys_pb2.DCSwitchSet(enable=int(enable))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x44, message=message
        )

    @controls.outlet(ac_ports, availability=dynamic(ac_ports_availability))
    async def enable_ac_ports(self, enable: bool):
        """Send command to enable/disable AC"""
        self._logger.debug("enable_ac_ports: %s", enable)

        # Current value from pb_heartbeat.show_flag bit 2
        if not self.ac_allowed:
            self._logger.warning("Cannot enable AC ports when AC is not allowed")
            return

        message = yj751_sys_pb2.ACDsgSet(enable=int(enable))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x48, message=message
        )

    async def enable_ac_xboost(self, enable: bool):
        """Send command to enable/disable AC XBoost"""
        self._logger.debug("set_ac_xboost: %s", enable)

        # Current value from pb_app_para_heartbeat.ac_xboost
        message = yj751_sys_pb2.ACDsgSet(xboost=int(enable))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x48, message=message
        )
        return True

    async def enable_battery_heating(self, enable: bool):
        """Send command to enable/disable battery preconditioning"""
        self._logger.debug("enable_battery_heating: %s", enable)

        # Current value from pb_app_para_heartbeat.bms_mode_set
        message = yj751_sys_pb2.BpHeatSet(en_bp_heat=int(enable))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x59, message=message
        )
        return True

    async def enable_ac_always_on(self, enable: bool):
        """Send command to enable/disable AC Always On"""
        self._logger.debug(
            "set_ac_always_on: %s, ac_often_open_min_soc: %s",
            enable,
            self.ac_always_on_soc_min,
        )

        # Current values from pb_app_para_heartbeat.ac_often_open and
        # pb_app_para_heartbeat.ac_often_open_min_soc. HV is bit 1 and LV is bit 0
        message = yj751_sys_pb2.AcOftenOpenCfg(
            ac_often_open=int(enable),
            ac_often_open_min_soc=0,
        )

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x5D, message=message
        )
        return True

    async def unpause_solar(self):
        """Send command to clear weak PV source flag"""
        self._logger.debug("unlock_pv_weak")

        # Current value from pb_display_property_upload.plug_in_info_pv_weak_source_flag
        message = yj751_sys_pb2.ConfigWrite(unlock_pv_weak=True)

        await self._send_command_packet(
            dst=0x02, cmd_func=0xFE, cmd_id=0x11, message=message
        )
        return True

    @controls.select(operating_mode_select, options=OperatingMode)
    async def set_operating_mode(self, mode: OperatingMode):
        """Send command to set operating mode"""
        self._logger.debug("set_operating_mode: %s", mode)

        # Current value from pb_app_para_heartbeat.sys_word_mode
        message = yj751_sys_pb2.ConfigWrite()
        cfg = message.cfg_energy_strategy_operate_mode
        cfg.operate_self_powered_open = mode == OperatingMode.SELF_POWERED
        cfg.operate_scheduled_open = mode == OperatingMode.SCHEDULED
        cfg.operate_tou_mode_open = mode == OperatingMode.TIME_OF_USE

        await self._send_command_packet(
            dst=0x02, cmd_func=0xFE, cmd_id=0x11, message=message
        )

    @controls.power(
        ac_c20_charging_power,
        min=600,
        max=1800,
        step=100,
        availability=dynamic(ac_c20_charging_power_availability),
    )
    async def set_ac_c20_charging_power(self, watts: float):
        """Send command to set C20 charging power"""
        self._logger.debug("set_ac_c20_charging_power: %s", watts)

        # Current value from pb_app_para_heartbeat.chg_c20_set_watts
        message = yj751_sys_pb2.ACChgSet(chg_c20_watts=int(watts))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x49, message=message
        )
        return True

    @controls.power(ac_5p8_charging_power, min=600, max=7200, step=100)
    async def set_ac_5p8_charging_power(self, watts: float):
        """Send command to set 5p8 port charging power"""
        self._logger.debug("set_ac_5p8_charging_power: %s", watts)

        # Current value from pb_app_para_heartbeat.chg_5p8_set_watts
        message = yj751_sys_pb2.ACChgSet(chg_5p8_watts=int(watts))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x49, message=message
        )
        return True

    @controls.battery(backup_discharge_limit, min=0, max=30)
    async def set_backup_discharge_limit(self, soc: float):
        """Send command to set backup discharge limit"""
        self._logger.debug("set_backup_discharge_limit: %s", soc)

        # Current value from pb_app_para_heartbeat.dsg_min_soc
        message = yj751_sys_pb2.DsgSocMinSet(min_dsg_soc=int(soc))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x58, message=message
        )
        return True

    @controls.battery(backup_charge_limit, min=50, max=100)
    async def set_backup_charge_limit(self, soc: float):
        """Send command to set backup charge limit"""
        self._logger.debug("set_backup_charge_limit: %s", soc)

        # Current value from pb_app_para_heartbeat.chg_max_soc
        message = yj751_sys_pb2.ChgSocMaxSet(max_chg_soc=int(soc))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x57, message=message
        )
        return True

    @controls.battery(backup_reserve_level, min=5, max=100)
    async def set_backup_reserve_level(self, soc: float):
        """Send command to set backup reserve level"""
        self._logger.debug("set_backup_reserve_level: %s", soc)

        # Current value from pb_app_para_heartbeat.sys_backup_soc
        message = yj751_sys_pb2.ConfigWrite(cfg_backup_reverse_soc=int(soc))

        await self._send_command_packet(
            dst=0x02, cmd_func=0xFE, cmd_id=0x11, message=message
        )
        return True

    async def set_power_standby_minutes(self, minutes: int):
        """Send command to set power standby minutes"""
        self._logger.debug("set_power_standby_mins: %s", minutes)

        # Current value from pb_app_para_heartbeat.power_standby_mins
        message = yj751_sys_pb2.PowerStandbySet(
            power_standby_min=_bracket(0, minutes, 1440)
        )

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x51, message=message
        )
        return True

    async def set_screen_standby_seconds(self, seconds: int):
        """Send command to set LCD standby seconds"""
        self._logger.debug("set_screen_standby_seconds: %s", seconds)

        # Current value from pb_app_para_heartbeat.screen_standby_sec
        message = yj751_sys_pb2.ScreenStandbySet(
            screen_standby_sec=_bracket(0, seconds, 1800)
        )

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x52, message=message
        )
        return True

    async def set_dc_standby_minutes(self, minutes: int):
        """Send command to set DC standby minutes"""
        self._logger.debug("set_dc_standby_mins: %s", minutes)

        # Current value from pb_app_para_heartbeat.dc_standby_mins
        message = yj751_sys_pb2.DCStandbySet(dc_standby_min=_bracket(0, minutes, 1440))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x54, message=message
        )
        return True

    async def set_ac_standby_minutes(self, minutes: int):
        """Send command to set AC standby minutes"""
        self._logger.debug("set_ac_standby_mins: %s", minutes)

        # Current value from pb_app_para_heartbeat.ac_standby_mins
        message = yj751_sys_pb2.ACStandbySet(ac_standby_min=_bracket(0, minutes, 1440))

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x53, message=message
        )
        return True

    async def request_heartbeat_info(self, param_type: int):
        """Send command to request heartbeat info"""
        # Report 8 = BackendRecordHeartbeatReport
        self._logger.debug("request_heartbeat_info: %s", param_type)

        message = yj751_sys_pb2.SystemParamGet(get_param_type=param_type)

        await self._send_command_packet(
            dst=0x02, cmd_func=0x02, cmd_id=0x67, message=message
        )
        return True

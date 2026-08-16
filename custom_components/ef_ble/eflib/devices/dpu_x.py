from collections.abc import Sequence

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..entity import controls
from ..packet import Packet
from ..pb import pd100_pb2
from ..props import (
    ProtobufProps,
    computed_field,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)
from ..props.enums import IntFieldValue
from ..props.transforms import flow_is_on, pround

pb = proto_attr_mapper(pd100_pb2.DisplayPropertyUpload)


class OperatingMode(IntFieldValue):
    UNKNOWN = -1

    NONE = 0
    SELF_POWERED = 1
    SCHEDULED = 2
    INTELLIGENT = 3


class _AcOutPower(repeated_pb_field_type(pb.pow_get_ac_out_list.pow_get_ac_out_item)):
    index: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.index], 2) if len(value) > self.index else None


class _AcOutCurrent(
    repeated_pb_field_type(pb.plug_in_info_ac_out_amp_list.plug_in_info_ac_out_amp_item)
):
    index: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.index], 2) if len(value) > self.index else None


class Device(DeviceBase, ProtobufProps):
    """Delta Pro Ultra X"""

    SN_PREFIX = (b"P101",)
    NAME_PREFIX = "EF-P10"

    battery_level = pb_field(pb.cms_batt_soc, pround(2))
    cell_temperature = pb_field(pb.cms_batt_temp)

    input_power = pb_field(pb.pow_in_sum_w, pround(2))
    output_power = pb_field(pb.pow_out_sum_w, pround(2))

    ac_input_power = pb_field(pb.pow_get_acp, pround(2))
    ac_input_voltage = pb_field(pb.plug_in_info_acp_vol, pround(2))
    ac_input_current = pb_field(pb.plug_in_info_acp_amp, pround(2))
    ac_charging_speed = pb_field(pb.plug_in_info_acp_chg_pow_max)
    plugged_in_ac = pb_field(pb.plug_in_info_ac_charger_flag)

    pv_power_1 = pb_field(pb.pow_get_pv, pround(2))
    pv_power_2 = pb_field(pb.pow_get_pv2, pround(2))
    pv_voltage_1 = pb_field(pb.plug_in_info_pv_vol, pround(2))
    pv_current_1 = pb_field(pb.plug_in_info_pv_amp, pround(2))
    pv_voltage_2 = pb_field(pb.plug_in_info_pv2_vol, pround(2))
    pv_current_2 = pb_field(pb.plug_in_info_pv2_amp, pround(2))

    remaining_time_charging = pb_field(pb.cms_chg_rem_time)
    remaining_time_discharging = pb_field(pb.cms_dsg_rem_time)

    error_code = pb_field(pb.errcode)

    wifi_rssi = pb_field(pb.module_wifi_rssi)
    dev_sleep_state = pb_field(pb.dev_sleep_state)

    ac_ports = pb_field(pb.flow_info_ac_out, flow_is_on)

    backup_charge_limit = pb_field(attr=pb.cms_max_chg_soc)
    backup_discharge_limit = pb_field(pb.cms_min_dsg_soc)
    backup_reserve_level = pb_field(pb.energy_backup_start_soc)

    _energy_strategy_operate_mode = pb_field(pb.energy_strategy_operate_mode)

    ac_nema_5_20_1_power = _AcOutPower(0)
    ac_nema_5_20_1_current = _AcOutCurrent(0)

    ac_nema_5_20_2_power = _AcOutPower(1)
    ac_nema_5_20_2_current = _AcOutCurrent(1)

    ac_nema_l14_30_power = _AcOutPower(2)
    ac_nema_l14_30_current = _AcOutCurrent(2)

    ac_nema_14_50_power = _AcOutPower(3)
    ac_nema_14_50_current = _AcOutCurrent(3)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    async def packet_parse(self, data: bytes):
        return Packet.from_bytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet):
        processed = False
        self.reset_updated()

        match packet.src, packet.cmd_set, packet.cmd_id:
            case 0x02, 0xFE, 0x15:
                self.update_from_bytes(pd100_pb2.DisplayPropertyUpload, packet.payload)
                processed = True
            case 0x35, 0x01, Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME:
                if len(packet.payload) == 0:
                    self._time_commands.async_send_all()
                processed = True
            case 0x35, 0x35, 0x20:
                # device-initiated BLE keepalive ping - no response expected
                processed = True
            case 0x30, 0x40, 0x30:
                # V4-framed BMS telemetry forwarded from a connected battery pack - the
                # inner protobuf schema is not in the EF Android app source, so we
                # ignore it for now
                processed = True

        self._notify_updated()

        return processed

    @computed_field
    def error_occurred(self) -> bool:
        return bool(self.error_code)

    @computed_field
    def operating_mode_select(self) -> OperatingMode:
        mode = self._energy_strategy_operate_mode
        if mode is None:
            return OperatingMode.NONE
        if mode.operate_self_powered_open:
            return OperatingMode.SELF_POWERED
        if mode.operate_scheduled_open:
            return OperatingMode.SCHEDULED
        if mode.operate_intelligent_schedule_mode_open:
            return OperatingMode.INTELLIGENT
        return OperatingMode.NONE

    @controls.outlet(ac_ports)
    async def enable_ac_ports(self, enabled: bool):
        await self._send_config_packet(pd100_pb2.ConfigWrite(cfg_ac_out_open=enabled))

    @controls.select(operating_mode_select, options=OperatingMode)
    async def set_operating_mode(self, mode: OperatingMode):
        message = pd100_pb2.ConfigWrite()
        cfg = message.cfg_energy_strategy_operate_mode
        cfg.operate_self_powered_open = mode == OperatingMode.SELF_POWERED
        cfg.operate_scheduled_open = mode == OperatingMode.SCHEDULED
        cfg.operate_intelligent_schedule_mode_open = mode == OperatingMode.INTELLIGENT
        await self._send_config_packet(message)

    @controls.power(ac_charging_speed, min=600, max=12000, step=100)
    async def set_ac_charging_speed(self, watts: float):
        await self._send_config_packet(
            pd100_pb2.ConfigWrite(cfg_plug_in_info_acp_chg_pow_max=int(watts))
        )
        return True

    @controls.battery(backup_charge_limit, min=50, max=100)
    async def set_backup_charge_limit(self, soc: float):
        await self._send_config_packet(pd100_pb2.ConfigWrite(cfg_max_chg_soc=int(soc)))
        return True

    @controls.battery(backup_discharge_limit, min=0, max=30)
    async def set_backup_discharge_limit(self, soc: float):
        await self._send_config_packet(pd100_pb2.ConfigWrite(cfg_min_dsg_soc=int(soc)))
        return True

    @controls.battery(backup_reserve_level, min=5, max=100)
    async def set_backup_reserve_level(self, soc: float):
        await self._send_config_packet(
            pd100_pb2.ConfigWrite(cfg_backup_reverse_soc=int(soc))
        )
        return True

    async def _send_config_packet(self, message: pd100_pb2.ConfigWrite):
        payload = message.SerializeToString()
        packet = Packet(0x21, 0x02, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self.send_packet(packet, raise_on_failure=True)

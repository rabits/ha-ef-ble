from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from google.protobuf.message import Message

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..entity import controls
from ..entity.base import dynamic
from ..packet import Packet
from ..pb import pd335_bms_bp_pb2, pd335_sys_pb2
from ..props import (
    ProtobufProps,
    computed_field,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)
from ..props.enums import IntFieldValue
from ..props.transforms import flow_is_on, out_power, pround

pb = proto_attr_mapper(pd335_sys_pb2.DisplayPropertyUpload)
pb_bms = proto_attr_mapper(pd335_bms_bp_pb2.BMSHeartBeatReport)


class _DcChargingMaxField(
    repeated_pb_field_type(
        list_field=pb.plug_in_info_pv_chg_max_list.pv_chg_max_item,
        value_field=lambda x: x.pv_chg_amp_max,
        per_item=True,
    )
):
    vol_type: int

    def get_value(self, item: pd335_sys_pb2.PvChgMaxItem) -> int | None:
        return item.pv_chg_amp_max if item.pv_chg_vol_type == self.vol_type else None


class _DcAmpSettingField(
    repeated_pb_field_type(
        list_field=pb.pv_dc_chg_setting_list.list_info,
        value_field=lambda x: x.pv_chg_amp_limit,
        per_item=True,
    )
):
    vol_type: int
    plug_index: int

    def get_value(self, item: pd335_sys_pb2.PvDcChgSetting) -> int | None:
        return (
            item.pv_chg_amp_limit
            if item.pv_plug_index == self.plug_index
            and item.pv_chg_vol_spec == self.vol_type
            else None
        )


class DCPortState(IntFieldValue):
    UNKNOWN = -1

    OFF = 0
    CAR = 1
    SOLAR = 2


class Delta3Base(DeviceBase, ProtobufProps):
    battery_level = pb_field(pb.cms_batt_soc, pround(2))
    battery_level_main = pb_field(pb.bms_batt_soc, pround(2))

    ac_input_power = pb_field(pb.pow_get_ac_in)
    ac_output_power = pb_field(pb.pow_get_ac_out, out_power)

    input_power = pb_field(pb.pow_in_sum_w)
    output_power = pb_field(pb.pow_out_sum_w)

    dc_port_input_power = pb_field(pb.pow_get_pv, pround(2))
    dc_port_state = pb_field(pb.plug_in_info_pv_type, DCPortState.from_value)

    usbc_output_power = pb_field(pb.pow_get_typec1, out_power)
    usbc2_output_power = pb_field(pb.pow_get_typec2, out_power)
    usba_output_power = pb_field(pb.pow_get_qcusb1, out_power)
    usba2_output_power = pb_field(pb.pow_get_qcusb2, out_power)

    plugged_in_ac = pb_field(pb.plug_in_info_ac_charger_flag)
    battery_input_power = pb_field(pb.pow_get_bms, lambda value: max(0, value))
    battery_output_power = pb_field(pb.pow_get_bms, lambda value: -min(0, value))

    battery_charge_limit_min = pb_field(pb.cms_min_dsg_soc)
    battery_charge_limit_max = pb_field(pb.cms_max_chg_soc)

    cell_temperature = pb_field(pb.bms_max_cell_temp)
    ac_ports = pb_field(pb.flow_info_ac_out, flow_is_on)

    remaining_time_charging = pb_field(pb.cms_chg_rem_time)
    remaining_time_discharging = pb_field(pb.cms_dsg_rem_time)

    error_code = pb_field(pb.errcode)

    ac_charging_speed = pb_field(pb.plug_in_info_ac_in_chg_pow_max)

    @computed_field
    def error_occurred(self) -> bool:
        return bool(self.error_code)

    @computed_field
    def max_ac_charging_power(self) -> int:
        return 1500

    @computed_field
    def solar_input_power(self) -> float:
        if (
            self.dc_port_state is DCPortState.SOLAR
            and self.dc_port_input_power is not None
        ):
            return round(self.dc_port_input_power, 2)
        return 0

    dc_charging_max_amps = _DcAmpSettingField(
        pd335_sys_pb2.PV_CHG_VOL_SPEC_12V, pd335_sys_pb2.PV_PLUG_INDEX_1
    )
    dc_charging_current_max = _DcChargingMaxField(pd335_sys_pb2.PV_CHG_VOL_SPEC_12V)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    async def data_parse(self, packet: Packet):
        processed = False
        self.reset_updated()

        if packet.src == 0x02 and packet.cmdSet == 0xFE and packet.cmdId == 0x15:
            self.update_from_bytes(pd335_sys_pb2.DisplayPropertyUpload, packet.payload)

            processed = True
        elif (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        self._notify_updated()

        return processed

    async def _send_config_packet(self, message: Message):
        payload = message.SerializeToString()
        packet = Packet(0x20, 0x02, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

    @controls.outlet(ac_ports)
    async def enable_ac_ports(self, enabled: bool):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_ac_out_open=enabled)
        )

    @controls.battery(battery_charge_limit_min, max=dynamic(battery_charge_limit_max))
    async def set_battery_charge_limit_min(self, limit: float):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_min_dsg_soc=int(limit))
        )
        return True

    @controls.battery(battery_charge_limit_max, min=dynamic(battery_charge_limit_min))
    async def set_battery_charge_limit_max(self, limit: float):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_max_chg_soc=int(limit))
        )
        return True

    @controls.power(ac_charging_speed, max=dynamic(max_ac_charging_power))
    async def set_ac_charging_speed(self, value: float):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(
                cfg_ac_in_chg_mode=pd335_sys_pb2.AC_IN_CHG_MODE_SELF_DEF_POW,
                cfg_plug_in_info_ac_in_chg_pow_max=int(value),
            )
        )
        return True

    @controls.current(dc_charging_max_amps, max=dynamic(dc_charging_current_max))
    async def set_dc_charging_amps_max(
        self,
        value: float,
        plug_index: pd335_sys_pb2.PV_PLUG_INDEX = pd335_sys_pb2.PV_PLUG_INDEX_1,
    ) -> bool:
        config = pd335_sys_pb2.ConfigWrite()
        config.cfg_pv_dc_chg_setting.pv_plug_index = plug_index
        config.cfg_pv_dc_chg_setting.pv_chg_vol_spec = pd335_sys_pb2.PV_CHG_VOL_SPEC_12V
        config.cfg_pv_dc_chg_setting.pv_chg_amp_limit = int(value)

        await self._send_config_packet(config)
        return True

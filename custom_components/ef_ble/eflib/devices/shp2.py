from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum

from ..commands import TimeCommands
from ..devicebase import AdvertisementData, BLEDevice, DeviceBase
from ..packet import Packet
from ..pb import pd303_pb2
from ..props import (
    Field,
    ProtobufProps,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)
from ..props.enums import IntFieldValue
from ..props.protobuf_field import TransformIfMissing

pb_time = proto_attr_mapper(pd303_pb2.ProtoTime)
pb_push_set = proto_attr_mapper(pd303_pb2.ProtoPushAndSet)


class ControlStatus(IntFieldValue):
    UNKNOWN = -1

    OFF = 0
    DISCHARGE = 1
    CHARGE = 2
    EMERGENCY_STOP = 3
    STANDBY = 4


class PowerStatus(IntFieldValue):
    UNKNOWN = -1

    GRID_POWER = 0
    BATTERY_POWER = 1
    OIL_POWER = 2
    EMERGENCY_STOP = 3
    OFF_POWER = 4


class PVStatus(IntFieldValue):
    UNKNOWN = -1

    NONE = 0
    LV = 1
    HV = 2
    LV_AND_HV = 3


class SmartBackupMode(IntFieldValue):
    NONE = 0
    TIME_OF_USE = 1
    SELF_POWERED = 2
    SCHEDULED = 3


class ChannelSetStatus(IntEnum):
    """
    Enum of values to send in the ch#_enable_set command to enable or disable a channel. Please note that these
    values ARE NOT the same as the values sent back by the panel in the ch#_enable_set response. The panel
    looks like it returns a 1 for enabled, but a 0 for all other states including disabled and disconnected.
    """

    ENABLE = 1
    DISABLE = 2


@dataclass
class CircuitPowerField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_watt)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return value[self.idx] if value and len(value) > self.idx else None


@dataclass
class CircuitCurrentField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_curr)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 4) if value and len(value) > self.idx else None


@dataclass
class ChannelPowerField(repeated_pb_field_type(list_field=pb_time.watt_info.ch_watt)):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 2) if value and len(value) > self.idx else None


def _errors(error_codes: pd303_pb2.ErrCode):
    return [e for e in error_codes.err_code if e != b"\x00\x00\x00\x00\x00\x00\x00\x00"]


def _is_value_present(value: int | None) -> bool:
    return value is not None


_hall1_incre_info = pb_push_set.load_incre_info.hall1_incre_info


class Device(DeviceBase, ProtobufProps):
    """Smart Home Panel 2"""

    SN_PREFIX = b"HD31"
    NAME_PREFIX = "EF-HD3"

    NUM_OF_CIRCUITS = 12
    NUM_OF_CHANNELS = 3

    power_status = pb_field(pb_push_set.power_sta, PowerStatus.from_value)
    battery_level = pb_field(pb_push_set.backup_incre_info.backup_bat_per)
    grid_status = pb_field(pb_push_set.master_incre_info.grid_sta)
    storm_mode = pb_field(pb_push_set.in_storm_mode)

    circuit_power_1 = CircuitPowerField(0)
    circuit_power_2 = CircuitPowerField(1)
    circuit_power_3 = CircuitPowerField(2)
    circuit_power_4 = CircuitPowerField(3)
    circuit_power_5 = CircuitPowerField(4)
    circuit_power_6 = CircuitPowerField(5)
    circuit_power_7 = CircuitPowerField(6)
    circuit_power_8 = CircuitPowerField(7)
    circuit_power_9 = CircuitPowerField(8)
    circuit_power_10 = CircuitPowerField(9)
    circuit_power_11 = CircuitPowerField(10)
    circuit_power_12 = CircuitPowerField(11)

    circuit_current_1 = CircuitCurrentField(0)
    circuit_current_2 = CircuitCurrentField(1)
    circuit_current_3 = CircuitCurrentField(2)
    circuit_current_4 = CircuitCurrentField(3)
    circuit_current_5 = CircuitCurrentField(4)
    circuit_current_6 = CircuitCurrentField(5)
    circuit_current_7 = CircuitCurrentField(6)
    circuit_current_8 = CircuitCurrentField(7)
    circuit_current_9 = CircuitCurrentField(8)
    circuit_current_10 = CircuitCurrentField(9)
    circuit_current_11 = CircuitCurrentField(10)
    circuit_current_12 = CircuitCurrentField(11)

    # Circuit state properties (on/off control)
    circuit_1 = pb_field(_hall1_incre_info.ch1_sta.load_sta)
    circuit_2 = pb_field(_hall1_incre_info.ch2_sta.load_sta)
    circuit_3 = pb_field(_hall1_incre_info.ch3_sta.load_sta)
    circuit_4 = pb_field(_hall1_incre_info.ch4_sta.load_sta)
    circuit_5 = pb_field(_hall1_incre_info.ch5_sta.load_sta)
    circuit_6 = pb_field(_hall1_incre_info.ch6_sta.load_sta)
    circuit_7 = pb_field(_hall1_incre_info.ch7_sta.load_sta)
    circuit_8 = pb_field(_hall1_incre_info.ch8_sta.load_sta)
    circuit_9 = pb_field(_hall1_incre_info.ch9_sta.load_sta)
    circuit_10 = pb_field(_hall1_incre_info.ch10_sta.load_sta)
    circuit_11 = pb_field(_hall1_incre_info.ch11_sta.load_sta)
    circuit_12 = pb_field(_hall1_incre_info.ch12_sta.load_sta)

    circuit_1_split_link = pb_field(_hall1_incre_info.ch1_info.splitphase.link_ch)
    circuit_2_split_link = pb_field(_hall1_incre_info.ch2_info.splitphase.link_ch)
    circuit_3_split_link = pb_field(_hall1_incre_info.ch3_info.splitphase.link_ch)
    circuit_4_split_link = pb_field(_hall1_incre_info.ch4_info.splitphase.link_ch)
    circuit_5_split_link = pb_field(_hall1_incre_info.ch5_info.splitphase.link_ch)
    circuit_6_split_link = pb_field(_hall1_incre_info.ch6_info.splitphase.link_ch)
    circuit_7_split_link = pb_field(_hall1_incre_info.ch7_info.splitphase.link_ch)
    circuit_8_split_link = pb_field(_hall1_incre_info.ch8_info.splitphase.link_ch)
    circuit_9_split_link = pb_field(_hall1_incre_info.ch9_info.splitphase.link_ch)
    circuit_10_split_link = pb_field(_hall1_incre_info.ch10_info.splitphase.link_ch)
    circuit_11_split_link = pb_field(_hall1_incre_info.ch11_info.splitphase.link_ch)
    circuit_12_split_link = pb_field(_hall1_incre_info.ch12_info.splitphase.link_ch)

    circuit_1_split_info_loaded = pb_field(
        _hall1_incre_info.ch1_info.splitphase.link_ch, _is_value_present
    )
    circuit_2_split_info_loaded = pb_field(
        _hall1_incre_info.ch2_info.splitphase.link_ch, _is_value_present
    )
    circuit_3_split_info_loaded = pb_field(
        _hall1_incre_info.ch3_info.splitphase.link_ch, _is_value_present
    )
    circuit_4_split_info_loaded = pb_field(
        _hall1_incre_info.ch4_info.splitphase.link_ch, _is_value_present
    )
    circuit_5_split_info_loaded = pb_field(
        _hall1_incre_info.ch5_info.splitphase.link_ch, _is_value_present
    )
    circuit_6_split_info_loaded = pb_field(
        _hall1_incre_info.ch6_info.splitphase.link_ch, _is_value_present
    )
    circuit_7_split_info_loaded = pb_field(
        _hall1_incre_info.ch7_info.splitphase.link_ch, _is_value_present
    )
    circuit_8_split_info_loaded = pb_field(
        _hall1_incre_info.ch8_info.splitphase.link_ch, _is_value_present
    )
    circuit_9_split_info_loaded = pb_field(
        _hall1_incre_info.ch9_info.splitphase.link_ch, _is_value_present
    )
    circuit_10_split_info_loaded = pb_field(
        _hall1_incre_info.ch10_info.splitphase.link_ch, _is_value_present
    )
    circuit_11_split_info_loaded = pb_field(
        _hall1_incre_info.ch11_info.splitphase.link_ch, _is_value_present
    )
    circuit_12_split_info_loaded = pb_field(
        _hall1_incre_info.ch12_info.splitphase.link_ch, _is_value_present
    )

    channel_power_1 = ChannelPowerField(0)
    channel_power_2 = ChannelPowerField(1)
    channel_power_3 = ChannelPowerField(2)

    # Input 1
    channel1_sn = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.dev_info.model_info.sn
    )
    channel1_type = pb_field(pb_push_set.backup_incre_info.Energy1_info.dev_info.type)
    channel1_capacity = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.dev_info.full_cap
    )
    channel1_rate_power = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.dev_info.rate_power
    )
    channel1_is_enabled = pb_field(pb_push_set.backup_incre_info.Energy1_info.is_enable)
    channel1_is_connected = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.is_connect
    )
    channel1_is_ac_open = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.is_ac_open
    )
    channel1_is_power_output = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.is_power_output
    )
    channel1_is_grid_charge = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.is_grid_charge
    )
    channel1_is_mppt_charge = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.is_mppt_charge
    )
    channel1_battery_percentage = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.battery_percentage
    )
    channel1_output_power = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.output_power
    )
    channel1_ems_charging = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.ems_chg_flag
    )
    channel1_hw_connect = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.hw_connect
    )
    channel1_battery_temp = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.ems_bat_temp
    )
    channel1_lcd_input = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.lcd_input_watts
    )
    channel1_pv_status = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.pv_charge_watts, PVStatus.from_value
    )
    channel1_pv_lv_input = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.pv_low_charge_watts
    )
    channel1_pv_hv_input = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.pv_height_charge_watts
    )
    channel1_error_code = pb_field(
        pb_push_set.backup_incre_info.Energy1_info.error_code_num
    )

    ch1_backup_is_ready = pb_field(
        pb_push_set.backup_incre_info.ch1_info.backup_is_ready
    )
    ch1_ctrl_status = pb_field(
        pb_push_set.backup_incre_info.ch1_info.ctrl_sta, ControlStatus.from_value
    )
    ch1_force_charge = pb_field(pb_push_set.backup_incre_info.ch1_info.force_charge_sta)
    ch1_backup_rly1_cnt = pb_field(
        pb_push_set.backup_incre_info.ch1_info.backup_rly1_cnt
    )
    ch1_backup_rly2_cnt = pb_field(
        pb_push_set.backup_incre_info.ch1_info.backup_rly2_cnt
    )
    ch1_wake_up_charge_status = pb_field(
        pb_push_set.backup_incre_info.ch1_info.wake_up_charge_sta
    )
    ch1_channel_5p8_type = pb_field(
        pb_push_set.backup_incre_info.ch1_info.energy_5p8_type
    )

    # Input 2
    channel2_sn = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.dev_info.model_info.sn
    )
    channel2_type = pb_field(pb_push_set.backup_incre_info.Energy2_info.dev_info.type)
    channel2_capacity = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.dev_info.full_cap
    )
    channel2_rate_power = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.dev_info.rate_power
    )
    channel2_is_enabled = pb_field(pb_push_set.backup_incre_info.Energy2_info.is_enable)
    channel2_is_connected = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.is_connect
    )
    channel2_is_ac_open = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.is_ac_open
    )
    channel2_is_power_output = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.is_power_output
    )
    channel2_is_grid_charge = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.is_grid_charge
    )
    channel2_is_mppt_charge = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.is_mppt_charge
    )
    channel2_battery_percentage = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.battery_percentage
    )
    channel2_output_power = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.output_power
    )
    channel2_ems_charging = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.ems_chg_flag
    )
    channel2_hw_connect = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.hw_connect
    )
    channel2_battery_temp = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.ems_bat_temp
    )
    channel2_lcd_input = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.lcd_input_watts
    )
    channel2_pv_status = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.pv_charge_watts, PVStatus.from_value
    )
    channel2_pv_lv_input = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.pv_low_charge_watts
    )
    channel2_pv_hv_input = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.pv_height_charge_watts
    )
    channel2_error_code = pb_field(
        pb_push_set.backup_incre_info.Energy2_info.error_code_num
    )

    ch2_backup_is_ready = pb_field(
        pb_push_set.backup_incre_info.ch2_info.backup_is_ready
    )
    ch2_ctrl_status = pb_field(
        pb_push_set.backup_incre_info.ch2_info.ctrl_sta, ControlStatus.from_value
    )
    ch2_force_charge = pb_field(pb_push_set.backup_incre_info.ch2_info.force_charge_sta)
    ch2_backup_rly1_cnt = pb_field(
        pb_push_set.backup_incre_info.ch2_info.backup_rly1_cnt
    )
    ch2_backup_rly2_cnt = pb_field(
        pb_push_set.backup_incre_info.ch2_info.backup_rly2_cnt
    )
    ch2_wake_up_charge_status = pb_field(
        pb_push_set.backup_incre_info.ch2_info.wake_up_charge_sta
    )
    ch2_channel_5p8_type = pb_field(
        pb_push_set.backup_incre_info.ch2_info.energy_5p8_type
    )

    # Input 3
    channel3_sn = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.dev_info.model_info.sn
    )
    channel3_type = pb_field(pb_push_set.backup_incre_info.Energy3_info.dev_info.type)
    channel3_capacity = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.dev_info.full_cap
    )
    channel3_rate_power = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.dev_info.rate_power
    )
    channel3_is_enabled = pb_field(pb_push_set.backup_incre_info.Energy3_info.is_enable)
    channel3_is_connected = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.is_connect
    )
    channel3_is_ac_open = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.is_ac_open
    )
    channel3_is_power_output = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.is_power_output
    )
    channel3_is_grid_charge = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.is_grid_charge
    )
    channel3_is_mppt_charge = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.is_mppt_charge
    )
    channel3_battery_percentage = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.battery_percentage
    )
    channel3_output_power = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.output_power
    )
    channel3_ems_charging = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.ems_chg_flag
    )
    channel3_hw_connect = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.hw_connect
    )
    channel3_battery_temp = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.ems_bat_temp
    )
    channel3_lcd_input = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.lcd_input_watts
    )
    channel3_pv_status = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.pv_charge_watts, PVStatus.from_value
    )
    channel3_pv_lv_input = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.pv_low_charge_watts
    )
    channel3_pv_hv_input = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.pv_height_charge_watts
    )
    channel3_error_code = pb_field(
        pb_push_set.backup_incre_info.Energy3_info.error_code_num
    )

    ch3_backup_is_ready = pb_field(
        pb_push_set.backup_incre_info.ch3_info.backup_is_ready
    )
    ch3_ctrl_status = pb_field(
        pb_push_set.backup_incre_info.ch3_info.ctrl_sta, ControlStatus.from_value
    )
    ch3_force_charge = pb_field(pb_push_set.backup_incre_info.ch3_info.force_charge_sta)
    ch3_backup_rly1_cnt = pb_field(
        pb_push_set.backup_incre_info.ch3_info.backup_rly1_cnt
    )
    ch3_backup_rly2_cnt = pb_field(
        pb_push_set.backup_incre_info.ch3_info.backup_rly2_cnt
    )
    ch3_wake_up_charge_status = pb_field(
        pb_push_set.backup_incre_info.ch3_info.wake_up_charge_sta
    )
    ch3_5p8_type = pb_field(pb_push_set.backup_incre_info.ch3_info.energy_5p8_type)

    in_use_power = pb_field(pb_time.watt_info.all_hall_watt)
    grid_power = pb_field(
        pb_time.watt_info.grid_watt,
        TransformIfMissing(lambda v: v if v is not None else 0.0),
    )

    smart_backup_mode = pb_field(
        pb_push_set.smart_backup_mode, SmartBackupMode.from_value
    )
    backup_enabled = pb_field(pb_push_set.backup_reserve_enable)
    backup_reserve_level = pb_field(pb_push_set.backup_reserve_soc)
    backup_charge_limit = pb_field(pb_push_set.foce_charge_hight)
    eps_mode = pb_field(pb_push_set.eps_mode_info)
    min_ac_charging_power = 500
    max_ac_charging_power = 7200
    ac_charging_speed_step = 100
    ac_charging_speed = pb_field(pb_push_set.charge_watt_power)

    errors = pb_field(pb_push_set.backup_incre_info.errcode, _errors)
    error_count = Field[int]()
    error_happened = Field[bool]()

    @staticmethod
    def check(sn):
        return sn.startswith(Device.SN_PREFIX)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)

        self._time_commands = TimeCommands(self)

    async def data_parse(self, packet: Packet) -> bool:
        """Processing the incoming notifications from the device"""
        processed = False
        self.reset_updated()

        prev_error_count = self.error_count

        if packet.src == 0x0B and packet.cmdSet == 0x0C:
            if (
                packet.cmdId == 0x01
            ):  # master_info, load_info, backup_info, watt_info, master_ver_info
                self._logger.debug("Parsed data: %r", packet)

                await self._conn.replyPacket(packet)
                self.update_from_bytes(pd303_pb2.ProtoTime, packet.payload)
                processed = True
            elif packet.cmdId == 0x20:  # backup_incre_info
                self._logger.debug("Parsed data: %r", packet)

                await self._conn.replyPacket(packet)
                self.update_from_bytes(pd303_pb2.ProtoPushAndSet, packet.payload)

                processed = True

            elif packet.cmdId == 0x21:  # is_get_cfg_flag
                self._logger.debug("Parsed data: %r", packet)
                self.update_from_bytes(pd303_pb2.ProtoPushAndSet, packet.payload)
                processed = True

        elif packet.src == 0x35 and packet.cmdSet == 0x35 and packet.cmdId == 0x20:
            self._logger.debug("Ping received: %r", packet)
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

        elif packet.src == 0x0B and packet.cmdSet == 0x01 and packet.cmdId == 0x55:
            # Device reply that it's online and ready
            self._conn._add_task(self.set_config_flag(True))
            processed = True

        self.error_count = len(self.errors) if self.errors is not None else None

        if (
            self.error_count is not None
            and prev_error_count is not None
            and self.error_count > prev_error_count
        ) or (self.error_count is not None and prev_error_count is None):
            self.error_happened = True
            self._logger.warning("Error happened on device: %s", self.errors)

        for field_name in self.updated_fields:
            try:
                self.update_callback(field_name)
                self.update_state(field_name, getattr(self, field_name))
            except Exception as e:  # noqa: BLE001
                self._logger.warning(
                    "Error happened while updating field %s: %s", field_name, e
                )

        return processed

    async def _send_config_packet(self, message):
        payload = message.SerializeToString()
        packet = Packet(0x21, 0x0B, 0x0C, 0x21, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

    async def set_config_flag(self, enable):
        """Send command to enable/disable sending config data from device to the host"""
        self._logger.debug("setConfigFlag: %s", enable)

        ppas = pd303_pb2.ProtoPushAndSet()
        ppas.is_get_cfg_flag = enable

        await self._send_config_packet(ppas)
        return True

    async def set_circuit_power(self, circuit_id: int, enable: bool):
        """Send command to power on / off the specific circuit of the panel"""
        self._logger.debug("setCircuitPower for %d: %s", circuit_id, enable)

        split_link = getattr(self, f"circuit_{circuit_id}_split_link", None)
        if split_link is None:
            self._logger.warning(
                "Cannot set circuit power for circuit %d because split circuit info is not available",
                circuit_id,
            )
            return None
        is_split = split_link != 0
        if is_split and (split_link < 1 or split_link > self.NUM_OF_CIRCUITS):
            self._logger.warning(
                "Cannot set circuit power for circuit %d because split link circuit id %d is invalid",
                circuit_id,
                split_link,
            )
            return None

        ppas = pd303_pb2.ProtoPushAndSet()
        sta = getattr(
            ppas.load_incre_info.hall1_incre_info, "ch" + str(circuit_id) + "_sta"
        )
        sta.load_sta = (
            pd303_pb2.LOAD_CH_POWER_ON if enable else pd303_pb2.LOAD_CH_POWER_OFF
        )
        sta.ctrl_mode = pd303_pb2.RLY_HAND_CTRL_MODE

        # If it's a split circuit, also set the linked circuit to the same state because they will be turned on/off together
        if is_split:
            sta2 = getattr(
                ppas.load_incre_info.hall1_incre_info, "ch" + str(split_link) + "_sta"
            )
            sta2.load_sta = (
                pd303_pb2.LOAD_CH_POWER_ON if enable else pd303_pb2.LOAD_CH_POWER_OFF
            )
            sta2.ctrl_mode = pd303_pb2.RLY_HAND_CTRL_MODE

        await self._send_config_packet(ppas)
        return True

    async def set_backup_reserve_level(self, value: int):
        self._logger.debug("set_backup_reserve_level: %d", value)

        ppas = pd303_pb2.ProtoPushAndSet()
        value = min(max(10, value), 50)
        ppas.backup_reserve_soc = value

        await self._send_config_packet(ppas)
        return True

    async def set_channel_enable(self, channel_id: int, value: bool):
        self._logger.debug("set_channel_enable: %d %s", channel_id, value)

        ppas = pd303_pb2.ProtoPushAndSet()
        setattr(
            ppas,
            f"ch{channel_id}_enable_set",
            ChannelSetStatus.ENABLE if value else ChannelSetStatus.DISABLE,
        )

        await self._send_config_packet(ppas)
        return True

    async def set_channel_force_charge(self, channel_id: int, value: bool):
        self._logger.debug("set_channel_force_charge: %d %s", channel_id, value)

        ppas = pd303_pb2.ProtoPushAndSet()
        setattr(
            ppas,
            f"ch{channel_id}_force_charge",
            pd303_pb2.FORCE_CHARGE_ON if value else pd303_pb2.FORCE_CHARGE_OFF,
        )
        # App disables operating mode for force charge, EPS mode is allowed, if enabled
        if value:
            ppas.smart_backup_mode = SmartBackupMode.NONE

        await self._send_config_packet(ppas)
        return True

    async def set_smart_backup_mode(self, mode: SmartBackupMode):
        self._logger.debug("set_smart_backup_mode: %d", mode.value)

        ppas = pd303_pb2.ProtoPushAndSet()
        ppas.smart_backup_mode = mode.value

        # App disable EPS Mode and disallows force charge when setting a Smart Backup Mode other than None
        if mode is not SmartBackupMode.NONE:
            ppas.eps_mode_info = False
            for channel_id in range(1, self.NUM_OF_CHANNELS + 1):
                if getattr(self, f"ch{channel_id}_force_charge"):
                    setattr(
                        ppas, f"ch{channel_id}_force_charge", pd303_pb2.FORCE_CHARGE_OFF
                    )

        await self._send_config_packet(ppas)
        return True

    async def set_eps_mode(self, value: bool):
        self._logger.debug("set_eps_mode: %d", value)

        if value and self.smart_backup_mode != SmartBackupMode.NONE:
            # App forces setting of operating mode to NONE when EPS is enabled.
            # We set this to NONE first or the SHP2 will sometimes report a grid outage if
            # we set it all in one PPS command.
            # Note: unlike operating mode force charge is allowed with EPS mode
            ppas_sbm = pd303_pb2.ProtoPushAndSet()
            ppas_sbm.smart_backup_mode = SmartBackupMode.NONE
            await self._send_config_packet(ppas_sbm)

        ppas = pd303_pb2.ProtoPushAndSet()

        ppas.eps_mode_info = value
        await self._send_config_packet(ppas)
        return True

    async def set_backup_charge_limit(self, value: int):
        self._logger.debug("set_backup_charge_limit: %d", value)

        ppas = pd303_pb2.ProtoPushAndSet()

        value = min(max(80, value), 100)
        ppas.foce_charge_hight = value  # key is misspelled by ecoflow

        await self._send_config_packet(ppas)
        return True

    async def set_ac_charging_speed(self, value: int):
        self._logger.debug("set_ac_charging_speed: %d", value)

        ppas = pd303_pb2.ProtoPushAndSet()

        # Round to nearest 100 and limit to allowed range
        value = min(
            max(
                self.min_ac_charging_power,
                int(value / self.ac_charging_speed_step) * self.ac_charging_speed_step,
            ),
            self.max_ac_charging_power,
        )
        ppas.charge_watt_power = value

        await self._send_config_packet(ppas)
        return True

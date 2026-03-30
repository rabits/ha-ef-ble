from collections.abc import Sequence
from enum import IntEnum

from ..commands import TimeCommands
from ..devicebase import AdvertisementData, BLEDevice, DeviceBase
from ..entity import controls
from ..entity.base import dynamic
from ..packet import Packet
from ..pb import pd303_pb2
from ..props import (
    Field,
    ProtobufProps,
    field_group,
    pb_field,
    pb_group,
    pb_indexed_attr,
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
    Enum of values to send in the ch#_enable_set command.

    Please note that these values ARE NOT the same as the values sent back by the panel
    in the ch#_enable_set response. The panel looks like it returns a 1 for enabled, but
    a 0 for all other states including disabled and disconnected.
    """

    ENABLE = 1
    DISABLE = 2


class CircuitPowerField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_watt)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return value[self.idx] if value and len(value) > self.idx else None


class CircuitCurrentField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_curr)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 4) if value and len(value) > self.idx else None


class ChannelPowerField(repeated_pb_field_type(list_field=pb_time.watt_info.ch_watt)):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 2) if value and len(value) > self.idx else None


def _errors(error_codes: pd303_pb2.ErrCode):
    return [e for e in error_codes.err_code if e != b"\x00\x00\x00\x00\x00\x00\x00\x00"]


_hall1 = pb_push_set.load_incre_info.hall1_incre_info
_channel_pb = pb_push_set.backup_incre_info.ch1_info
_energy = pb_push_set.backup_incre_info.Energy1_info

_circuit_sta_group = pb_group("ch{n}_sta")
_circuit_info_group = pb_group("ch{n}_info")
_channel_group = pb_group("ch{n}_info", name_prefix="ch{n}")
_energy_group = pb_group("Energy{n}_info", name_prefix="channel{n}")


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

    circuit_power = field_group(lambda n: CircuitPowerField(n - 1), count=12)
    circuit_current = field_group(lambda n: CircuitCurrentField(n - 1), count=12)

    circuit = _circuit_sta_group(_hall1.ch1_sta.load_sta)
    circuit_split_link = _circuit_info_group(_hall1.ch1_info.splitphase.link_ch)
    circuit_split_info_loaded = _circuit_info_group(
        _hall1.ch1_info.splitphase.link_ch, transform=lambda value: value is not None
    )

    channel_power = field_group(lambda n: ChannelPowerField(n - 1), count=3)

    channel_sn = _energy_group(_energy.dev_info.model_info.sn)
    channel_type = _energy_group(_energy.dev_info.type)
    channel_capacity = _energy_group(_energy.dev_info.full_cap)
    channel_rate_power = _energy_group(_energy.dev_info.rate_power)
    channel_is_enabled = _energy_group(_energy.is_enable)
    channel_is_connected = _energy_group(_energy.is_connect)
    channel_is_ac_open = _energy_group(_energy.is_ac_open)
    channel_is_power_output = _energy_group(_energy.is_power_output)
    channel_is_grid_charge = _energy_group(_energy.is_grid_charge)
    channel_is_mppt_charge = _energy_group(_energy.is_mppt_charge)
    channel_battery_percentage = _energy_group(_energy.battery_percentage)
    channel_output_power = _energy_group(_energy.output_power)
    channel_ems_charging = _energy_group(_energy.ems_chg_flag)
    channel_hw_connect = _energy_group(_energy.hw_connect)
    channel_battery_temp = _energy_group(_energy.ems_bat_temp)
    channel_lcd_input = _energy_group(_energy.lcd_input_watts)
    channel_pv_status = _energy_group(
        _energy.pv_charge_watts,
        transform=PVStatus.from_value,
    )
    channel_pv_lv_input = _energy_group(_energy.pv_low_charge_watts)
    channel_pv_hv_input = _energy_group(_energy.pv_height_charge_watts)
    channel_error_code = _energy_group(_energy.error_code_num)

    ch_backup_is_ready = _channel_group(_channel_pb.backup_is_ready)
    ch_ctrl_status = _channel_group(
        _channel_pb.ctrl_sta,
        transform=ControlStatus.from_value,
    )
    ch_force_charge = _channel_group(_channel_pb.force_charge_sta)
    ch_backup_rly1_cnt = _channel_group(_channel_pb.backup_rly1_cnt)
    ch_backup_rly2_cnt = _channel_group(_channel_pb.backup_rly2_cnt)
    ch_wake_up_charge_status = _channel_group(
        _channel_pb.wake_up_charge_sta,
    )
    ch_5p8_type = _channel_group(_channel_pb.energy_5p8_type)

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
    backup_reserve_level_min = 10
    backup_reserve_level_max = 50
    backup_reserve_level_availability = pb_field(
        pb_push_set.backup_reserve_soc, lambda v: v is not None
    )
    backup_charge_limit = pb_field(pb_push_set.foce_charge_hight)
    backup_charge_limit_min = 80
    backup_charge_limit_max = 100
    backup_charge_limit_availability = pb_field(
        pb_push_set.foce_charge_hight, lambda v: v is not None
    )
    eps_mode = pb_field(pb_push_set.eps_mode_info)
    min_ac_charging_power = 500
    max_ac_charging_power = 7200
    ac_charging_speed_step = 100
    ac_charging_speed = pb_field(pb_push_set.charge_watt_power)

    errors = pb_field(pb_push_set.backup_incre_info.errcode, _errors)
    error_count = Field[int]()
    error_happened = Field[bool]()

    @staticmethod
    def check(sn: bytes):
        return sn.startswith(Device.SN_PREFIX)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)

        self._time_commands = TimeCommands(self)

    async def data_parse(self, packet: Packet) -> bool:
        """Proces the incoming notifications from the device"""
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

    @controls.for_each(
        circuit,
        control=controls.outlet,
        availability=circuit_split_info_loaded,
        translation_key="circuit_is_enabled",
        translation_placeholders=lambda i: {"circuit": str(i)},
    )
    async def set_circuit_power(self, circuit_id: int, enable: bool):
        """Send command to power on / off the specific circuit of the panel"""
        self._logger.debug("setCircuitPower for %d: %s", circuit_id, enable)

        split_link = self.circuit_split_link[circuit_id]
        if split_link is None:
            self._logger.warning(
                (
                    "Cannot set circuit power for circuit %d because split circuit "
                    "info is not available"
                ),
                circuit_id,
            )
            return None

        is_split = split_link != 0
        if is_split and (split_link < 1 or split_link > self.NUM_OF_CIRCUITS):
            self._logger.warning(
                (
                    "Cannot set circuit power for circuit %d because split link "
                    "circuit id %d is invalid"
                ),
                circuit_id,
                split_link,
            )
            return None

        ppas = pd303_pb2.ProtoPushAndSet()
        load_sta = pd303_pb2.LOAD_CH_POWER_ON if enable else pd303_pb2.LOAD_CH_POWER_OFF
        ch_sta = pb_indexed_attr(
            ppas, pb_push_set.load_incre_info.hall1_incre_info.ch1_sta, "ch{n}_sta"
        )

        sta = ch_sta[circuit_id]
        sta.load_sta = load_sta
        sta.ctrl_mode = pd303_pb2.RLY_HAND_CTRL_MODE

        # If it's a split circuit, also set the linked circuit to the same state
        if is_split:
            sta2 = ch_sta[split_link]
            sta2.load_sta = load_sta
            sta2.ctrl_mode = pd303_pb2.RLY_HAND_CTRL_MODE

        await self._send_config_packet(ppas)
        return True

    @controls.battery(
        backup_reserve_level,
        min=backup_reserve_level_min,
        max=backup_reserve_level_max,
        availability=dynamic(backup_reserve_level_availability),
    )
    async def set_backup_reserve_level(self, value: float):
        self._logger.debug("set_backup_reserve_level: %d", value)

        ppas = pd303_pb2.ProtoPushAndSet()
        value = min(
            max(self.backup_reserve_level_min, int(value)),
            self.backup_reserve_level_max,
        )
        ppas.backup_reserve_soc = value

        await self._send_config_packet(ppas)
        return True

    @controls.for_each(
        channel_is_enabled,
        control=controls.switch,
        availability=channel_is_connected,
        translation_key="channel_is_enabled",
        translation_placeholders=lambda i: {"channel": str(i)},
    )
    async def set_channel_enable(self, channel_id: int, value: bool):
        self._logger.debug("set_channel_enable: %d %s", channel_id, value)

        ppas = pd303_pb2.ProtoPushAndSet()
        ch_enable = pb_indexed_attr(
            ppas, pb_push_set.ch1_enable_set, "ch{n}_enable_set"
        )
        ch_enable[channel_id] = (
            ChannelSetStatus.ENABLE if value else ChannelSetStatus.DISABLE
        )

        await self._send_config_packet(ppas)
        return True

    @controls.for_each(
        ch_force_charge,
        control=controls.switch,
        availability=channel_is_connected,
        translation_key="ch_force_charge",
        translation_placeholders=lambda i: {"channel": str(i)},
    )
    async def set_channel_force_charge(self, channel_id: int, value: bool):
        self._logger.debug("set_channel_force_charge: %d %s", channel_id, value)

        ppas = pd303_pb2.ProtoPushAndSet()
        ch_force = pb_indexed_attr(
            ppas, pb_push_set.ch1_force_charge, "ch{n}_force_charge"
        )
        ch_force[channel_id] = (
            pd303_pb2.FORCE_CHARGE_ON if value else pd303_pb2.FORCE_CHARGE_OFF
        )
        # App disables operating mode for force charge, EPS mode is allowed, if enabled
        if value:
            ppas.smart_backup_mode = SmartBackupMode.NONE

        await self._send_config_packet(ppas)
        return True

    @controls.select(smart_backup_mode, options=SmartBackupMode)
    async def set_smart_backup_mode(self, mode: SmartBackupMode):
        self._logger.debug("set_smart_backup_mode: %d", mode.value)

        ppas = pd303_pb2.ProtoPushAndSet()
        ppas.smart_backup_mode = mode.value

        # App disables EPS Mode and disallows force charge when setting a Smart Backup
        # Mode other than None
        if mode is not SmartBackupMode.NONE:
            ppas.eps_mode_info = False
            for channel_id in range(1, self.NUM_OF_CHANNELS + 1):
                if self.ch_force_charge[channel_id]:
                    ch_info = pb_indexed_attr(
                        ppas,
                        pb_push_set.backup_incre_info.ch1_info,
                        "ch{n}_info",
                    )
                    ch_info[channel_id].force_charge_sta = pd303_pb2.FORCE_CHARGE_OFF

        await self._send_config_packet(ppas)

    @controls.switch(eps_mode)
    async def set_eps_mode(self, value: bool):
        self._logger.debug("set_eps_mode: %d", value)

        if value and self.smart_backup_mode != SmartBackupMode.NONE:
            # App forces setting of operating mode to NONE when EPS is enabled. We set
            # this to NONE first or the SHP2 will sometimes # report a grid outage if we
            # set it all in one PPS command.  # Note: unlike operating mode force charge
            # is allowed with EPS mode
            ppas_sbm = pd303_pb2.ProtoPushAndSet()
            ppas_sbm.smart_backup_mode = SmartBackupMode.NONE
            await self._send_config_packet(ppas_sbm)

        ppas = pd303_pb2.ProtoPushAndSet()

        ppas.eps_mode_info = value
        await self._send_config_packet(ppas)

    @controls.battery(
        backup_charge_limit,
        min=backup_charge_limit_min,
        max=backup_charge_limit_max,
        availability=dynamic(backup_charge_limit_availability),
    )
    async def set_backup_charge_limit(self, value: float):
        self._logger.debug("set_backup_charge_limit: %d", value)

        ppas = pd303_pb2.ProtoPushAndSet()

        value = min(
            max(self.backup_charge_limit_min, int(value)),
            self.backup_charge_limit_max,
        )
        ppas.foce_charge_hight = value  # key is misspelled by ecoflow

        await self._send_config_packet(ppas)
        return True

    @controls.power(
        ac_charging_speed,
        min=min_ac_charging_power,
        max=max_ac_charging_power,
        step=ac_charging_speed_step,
    )
    async def set_ac_charging_speed(self, value: float):
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

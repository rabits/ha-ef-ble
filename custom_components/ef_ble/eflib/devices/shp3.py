import dataclasses
import time
from enum import IntEnum

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from google.protobuf.message import Message

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..entity import controls
from ..entity.base import dynamic
from ..packet import Packet, PacketV4
from ..pb import dev_apl_comm_pb2
from ..props import (
    ProtobufProps,
    computed_field,
    pb_field,
    pb_field_group,
    pb_indexed_attr,
    proto_attr_mapper,
)
from ..props.enums import IntFieldValue
from ..props.protobuf_field import TransformIfMissing
from ..props.transforms import pround

pb = proto_attr_mapper(dev_apl_comm_pb2.DisplayPropertyUpload)
pb_cfg = proto_attr_mapper(dev_apl_comm_pb2.ConfigWrite)


class CircuitControl(IntEnum):
    ON = 1
    OFF = 2


class GridStatus(IntFieldValue):
    UNKNOWN = -1

    NOT_VALID = 0
    GRID_IN = 1
    GRID_OFFLINE = 2
    FEED_GRID = 3


class CircuitStatus(IntFieldValue):
    """Per-circuit relay status from `LoadChSta.load_sta` (`LOAD_CH_STA`)"""

    UNKNOWN = -1  # LOAD_CH_UNKNOWN_STA (4) and any unrecognized value

    OFF = 0
    ON_GRID = 1
    ON_BACK = 2
    EM_STOP = 3


class OperatingMode(IntFieldValue):
    """SHP3 energy-strategy operating mode (`CfgEnergyStrategyOperateMode` subfields)"""

    UNKNOWN = -1

    NONE = 0  # no operating mode selected ("Backup")
    SELF_POWERED = 1
    SCHEDULED = 2
    INTELLIGENT = 6


class BackupChannelType(IntFieldValue):
    UNKNOWN = -1

    NONE = 0
    BATTERY = 1
    OIL = 2
    STATION_CHARGER = 3


def _operating_mode_from_message(
    message: (
        dev_apl_comm_pb2.CfgEnergyStrategyOperateMode
        | dev_apl_comm_pb2.CfgPanelEnergyStrategyOperateMode
    ),
) -> OperatingMode:
    if message.operate_self_powered_open:
        return OperatingMode.SELF_POWERED
    if message.operate_scheduled_open:
        return OperatingMode.SCHEDULED
    if message.operate_intelligent_schedule_mode_open:
        return OperatingMode.INTELLIGENT
    return OperatingMode.NONE


def _channel_enabled(info: dev_apl_comm_pb2.BackupChInfo) -> bool | None:
    if not info.ch_dev_type:
        return None
    return info.ch_sta == 1


def _channel_type(info: dev_apl_comm_pb2.BackupChInfo) -> "BackupChannelType | None":
    if not info.ch_dev_type:
        return None
    return BackupChannelType.from_value(info.ch_dev_type)


def _channel_force_charging(info: dev_apl_comm_pb2.BackupChInfo) -> bool | None:
    if not info.ch_dev_type:
        return None
    return info.force_chg_sta == 1


def _channel_signal_connected(info: dev_apl_comm_pb2.BackupChInfo) -> bool | None:
    if not info.ch_dev_type:
        return None
    return info.signal_line_sta == 1


class Device(DeviceBase, ProtobufProps):
    """Smart Home Panel 3"""

    SN_PREFIX = (b"HR62", b"HR63", b"HR6C")
    NAME_PREFIX = "EF-SHP3"

    NUM_OF_CIRCUITS = 32
    NUM_OF_CHANNELS = 3
    _KEEPALIVE_INTERVAL = 20

    battery_level = pb_field(pb.cms_batt_soc, pround(2))
    remaining_time_charging = pb_field(pb.cms_chg_rem_time)
    remaining_time_discharging = pb_field(pb.cms_dsg_rem_time)

    battery_charge_limit_min = pb_field(pb.cms_min_dsg_soc)
    battery_charge_limit_max = pb_field(pb.cms_max_chg_soc)
    backup_reserve_level = pb_field(pb.backup_reverse_soc)

    l1_power = pb_field(pb.grid_connection_power_L1, pround(2))
    l2_power = pb_field(pb.grid_connection_power_L2, pround(2))
    l3_power = pb_field(pb.grid_connection_power_L3, pround(2))

    l1_voltage = pb_field(pb.grid_connection_vol_L1, pround(1))
    l2_voltage = pb_field(pb.grid_connection_vol_L2, pround(1))
    l3_voltage = pb_field(pb.grid_connection_vol_L3, pround(1))

    l1_current = pb_field(pb.grid_connection_amp_L1, pround(2))
    l2_current = pb_field(pb.grid_connection_amp_L2, pround(2))
    l3_current = pb_field(pb.grid_connection_amp_L3, pround(2))

    grid_connection_status = pb_field(pb.grid_connection_sta, GridStatus.from_value)
    grid_is_energized = pb_field(pb.grid_is_energized)

    circuit_power = pb_field_group(
        pb.load_ch1_sample_info.load_ch_power,
        match="load_ch{n}_sample_info",
        count=NUM_OF_CIRCUITS,
        transform=pround(2),
        name_template="circuit_power_{n}",
    )
    circuit_current = pb_field_group(
        pb.load_ch1_sample_info.load_ch_curr,
        match="load_ch{n}_sample_info",
        count=NUM_OF_CIRCUITS,
        transform=pround(2),
        name_template="circuit_current_{n}",
    )
    circuit_voltage = pb_field_group(
        pb.load_ch1_sample_info.load_ch_vol,
        match="load_ch{n}_sample_info",
        count=NUM_OF_CIRCUITS,
        transform=pround(1),
        name_template="circuit_voltage_{n}",
    )

    circuit_status = pb_field_group(
        pb.load_ch1_sta.load_sta,
        match="load_ch{n}_sta",
        count=NUM_OF_CIRCUITS,
        transform=TransformIfMissing(lambda v: CircuitStatus.from_value(v or 0)),
        name_template="circuit_status_{n}",
    )
    circuit_is_enabled = pb_field_group(
        pb.load_ch1_sta.load_sta,
        match="load_ch{n}_sta",
        count=NUM_OF_CIRCUITS,
        transform=TransformIfMissing(lambda v: (v or 0) in (1, 2)),
        name_template="circuit_is_enabled_{n}",
    )
    circuit_name = pb_field_group(
        pb.load_ch1_sta.ch_name,
        match="load_ch{n}_sta",
        count=NUM_OF_CIRCUITS,
        name_template="circuit_name_{n}",
    )
    circuit_split_link = pb_field_group(
        pb.load_ch1_sta.splitphase.link_ch,
        match="load_ch{n}_sta",
        count=NUM_OF_CIRCUITS,
        name_template="circuit_split_link_{n}",
    )
    circuit_split_info_loaded = pb_field_group(
        pb.load_ch1_sta.splitphase.link_ch,
        match="load_ch{n}_sta",
        count=NUM_OF_CIRCUITS,
        transform=lambda value: value is not None,
        name_template="circuit_split_info_loaded_{n}",
    )

    load_system = pb_field(pb.pow_get_sys_load, pround(2))
    load_from_grid = pb_field(pb.pow_get_sys_grid, pround(2))
    battery_power = pb_field(pb.pow_get_bp_cms, pround(2))
    pv_power_sum = pb_field(pb.pow_get_pv_sum, pround(2))

    # Per-channel enable state, driving the switch control below. ch_sta is the
    # enable/connected status (None for an empty channel); the switch writes ctrl_en.
    channel_is_enabled = pb_field_group(
        pb.panel_backup_ch1_Info,
        match="panel_backup_ch{n}_Info",
        count=NUM_OF_CHANNELS,
        transform=_channel_enabled,
        name_template="ch{n}_is_enabled",
    )

    channel_type = pb_field_group(
        pb.panel_backup_ch1_Info,
        match="panel_backup_ch{n}_Info",
        count=NUM_OF_CHANNELS,
        transform=_channel_type,
        name_template="ch{n}_type",
    )
    channel_force_charge = pb_field_group(
        pb.panel_backup_ch1_Info,
        match="panel_backup_ch{n}_Info",
        count=NUM_OF_CHANNELS,
        transform=_channel_force_charging,
        name_template="ch{n}_force_charge",
    )
    channel_signal_line = pb_field_group(
        pb.panel_backup_ch1_Info,
        match="panel_backup_ch{n}_Info",
        count=NUM_OF_CHANNELS,
        transform=_channel_signal_connected,
        name_template="ch{n}_signal_line",
    )

    ac_charging_speed = pb_field(pb.panel_max_charge_pow_set)
    min_ac_charging_power = 600
    max_ac_charging_power = 12000
    ac_charging_speed_step = 100

    storm_guard = pb_field(pb.storm_pattern_enable)

    _mode_panel = pb_field(
        pb.panle_energy_strategy_operate_mode, _operating_mode_from_message
    )
    _mode_generic = pb_field(
        pb.energy_strategy_operate_mode, _operating_mode_from_message
    )
    _eps_mode = pb_field(
        pb.panle_energy_strategy_operate_mode.operate_eps_mode,
        TransformIfMissing(bool),
    )
    _mix_scheduled = pb_field(
        pb.panle_energy_strategy_operate_mode.operate_mix_scheduled_open,
        TransformIfMissing(bool),
    )

    @computed_field
    def operating_mode_select(self) -> OperatingMode | None:
        if self._mode_panel is not None:
            return self._mode_panel
        return self._mode_generic

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)
        self._routing = _StandardProtocolRouting(sn)
        self.add_timer_task(self._send_keepalive, interval=self._KEEPALIVE_INTERVAL)
        self._userid_sent = False

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    async def _send_keepalive(self) -> None:
        await self._time_commands.sendRTCCheck()

    async def _send_userid_registration(self) -> None:
        user_id = (getattr(self._conn, "_user_id", "") or "").encode("ascii")
        userid_field_len = 64
        payload = (
            bytes([0x01])
            + user_id[:userid_field_len].ljust(userid_field_len, b"\x00")
            + int(time.time()).to_bytes(4, "little")
        )
        packet = Packet(
            src=0x21,
            dst=0x35,
            cmd_set=0x35,
            cmd_id=0xA8,
            payload=payload,
            dsrc=0x01,
            ddst=0x01,
            version=0x03,
        )
        await self._conn.sendPacket(packet, wait_for_response=False)

    async def packet_parse(self, data: bytes):
        return Packet.from_bytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        self.reset_updated()

        match packet.version, packet.src, packet.cmd_set, packet.cmd_id:
            case 0x04, 0x32, 0x40, 0x30:
                if isinstance(packet, PacketV4):
                    self._routing.remember_post(packet)
                _, body = self._routing.split(packet.payload)
                self.update_from_bytes(dev_apl_comm_pb2.DisplayPropertyUpload, body)
                processed = True
            case 0x04, _, 0x40, 0x30:
                # sub device update (per-battery telemetry forwarded by the panel)
                processed = True
            case _, 0x35, 0x01, Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME:
                if len(packet.payload) == 0:
                    self._time_commands.async_send_all()
                    if not self._userid_sent:
                        self._userid_sent = True
                        await self._send_userid_registration()
                processed = True
            case _, 0x35, 0x35, 0x20:
                await self._conn.replyPacket(packet)
                processed = True

        self._notify_updated()
        return processed

    async def _send_config_packet(self, message: Message):
        packet = self._routing.write_packet(message.SerializeToString())
        await self._conn.sendPacket(packet)

    @controls.battery(
        battery_charge_limit_min,
        max=dynamic(battery_charge_limit_max),
    )
    async def set_battery_charge_limit_min(self, limit: float):
        await self._send_config_packet(
            dev_apl_comm_pb2.ConfigWrite(cfg_min_dsg_soc=int(limit))
        )
        return True

    @controls.battery(
        battery_charge_limit_max,
        min=dynamic(battery_charge_limit_min),
    )
    async def set_battery_charge_limit_max(self, limit: float):
        await self._send_config_packet(
            dev_apl_comm_pb2.ConfigWrite(cfg_max_chg_soc=int(limit))
        )
        return True

    @controls.battery(backup_reserve_level, max=100)
    async def set_backup_reserve_level(self, value: float):
        await self._send_config_packet(
            dev_apl_comm_pb2.ConfigWrite(cfg_backup_reverse_soc=int(value))
        )
        return True

    @controls.power(
        ac_charging_speed,
        min=min_ac_charging_power,
        max=max_ac_charging_power,
        step=ac_charging_speed_step,
    )
    async def set_ac_charging_speed(self, value: float):
        watts = int(value) // self.ac_charging_speed_step * self.ac_charging_speed_step
        await self._send_config_packet(
            dev_apl_comm_pb2.ConfigWrite(cfg_panel_max_charge_pow_set=watts)
        )
        return True

    @controls.for_each(
        circuit_is_enabled,
        control=controls.outlet,
        availability=circuit_split_info_loaded,
        translation_key="circuit_is_enabled",
        translation_placeholders=lambda i: {"circuit": str(i)},
    )
    async def set_circuit_power(self, circuit_id: int, enable: bool):
        self._logger.debug("set_circuit_power for %d: %s", circuit_id, enable)

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

        config = dev_apl_comm_pb2.ConfigWrite()
        state = CircuitControl.ON if enable else CircuitControl.OFF
        ctrl = pb_indexed_attr(
            config, pb_cfg.cfg_load_ch1_ctrl_info, "cfg_load_ch{n}_ctrl_info"
        )

        ch = ctrl[circuit_id]
        ch.chanel_enable_ctrl = state
        ch.ctrl_mode = dev_apl_comm_pb2.LOAD_RLY_CTRL_MODE_HAND

        if is_split:
            ch_link = ctrl[split_link]
            ch_link.chanel_enable_ctrl = state
            ch_link.ctrl_mode = dev_apl_comm_pb2.LOAD_RLY_CTRL_MODE_HAND

        await self._send_config_packet(config)
        return True

    @controls.select(operating_mode_select, options=OperatingMode)
    async def set_operating_mode(self, mode: OperatingMode):
        if mode is OperatingMode.UNKNOWN:
            return

        config = dev_apl_comm_pb2.ConfigWrite()
        message = config.cfg_panle_energy_strategy_operate_mode
        message.operate_self_powered_open = mode is OperatingMode.SELF_POWERED
        message.operate_scheduled_open = mode is OperatingMode.SCHEDULED
        message.operate_intelligent_schedule_mode_open = (
            mode is OperatingMode.INTELLIGENT
        )
        message.operate_eps_mode = bool(self._eps_mode)
        message.operate_mix_scheduled_open = bool(self._mix_scheduled)

        await self._send_config_packet(config)

    @controls.switch(storm_guard)
    async def set_storm_guard(self, enable: bool):
        config = dev_apl_comm_pb2.ConfigWrite()
        config.cfg_storm_pattern.storm_pattern_enable = enable
        await self._send_config_packet(config)

    @controls.for_each(
        channel_is_enabled,
        control=controls.switch,
        translation_key="channel_is_enabled",
        translation_placeholders=lambda i: {"channel": str(i)},
    )
    async def set_channel_enable(self, channel_id: int, enable: bool):
        """
        Enable / disable a backup channel via `cfg_panel_backup_ch{N}_ctrl`.

        `BackupCtrl` carries both the channel enable (ctrl_en) and the force-charge
        toggle (ctrl_force_chg), and the panel applies them together, so we send the
        current force-charge state alongside the new enable value (on = 1, off = 2).
        """
        config = dev_apl_comm_pb2.ConfigWrite()
        ctrl = pb_indexed_attr(
            config, pb_cfg.cfg_panel_backup_ch1_ctrl, "cfg_panel_backup_ch{n}_ctrl"
        )
        backup = ctrl[channel_id]
        backup.ctrl_en = 1 if enable else 2
        backup.ctrl_force_chg = 1 if self.channel_force_charge[channel_id] else 2
        await self._send_config_packet(config)


class _StandardProtocolRouting:
    """
    SHP3 standard-protocol routing layer that wraps the protobuf inside the v4 payload.

    Reads: the v4 application payload is a routing header (the device-side SN fragment
    plus a 13-byte envelope) followed by the `DisplayPropertyUpload` protobuf.

    Writes:  mirror the latest telemetry post's v4 frame - reusing its session
    obfuscation, addressing and inner header via `dataclasses.replace` - and only
    override cmd_flags / is_ack / is_rw_cmd and the application payload. The payload is
    `serial9 + full_serial16 + envelope + ConfigWrite`, where the envelope is `40 03 03
    <seq> FE 11 00 21 01 0B 01` (FE 11 = PROPERTY_WRITE). Before any post is seen it
    falls back to a plain v3 frame.
    """

    HEADER_LEN = 22  # device SN fragment (9) + envelope (13), on reads
    _SERIAL_FRAGMENT_LEN = 9
    _WRITE_CMD_FLAGS = 0x10
    _WRITE_ENVELOPE_PREFIX = bytes([0x40, 0x03, 0x03])
    _WRITE_ENVELOPE_MID = bytes(
        [0xFE, 0x11, 0x00]
    )  # cmd_set 0xFE, cmd_id 0x11, reserved
    _WRITE_ENVELOPE_SUFFIX = bytes([0x21, 0x01, 0x0B, 0x01])

    def __init__(self, serial: str) -> None:
        self._serial = serial
        self._post_template: PacketV4 | None = None
        self._envelope_template: bytes | None = None
        self._write_seq = 0x20

    @classmethod
    def split(cls, payload: bytes) -> tuple[str, bytes]:
        """Split a v4 application payload into (device SN fragment, protobuf body)"""
        serial = payload[: cls._SERIAL_FRAGMENT_LEN].decode("ascii", errors="replace")
        return serial, payload[cls.HEADER_LEN :]

    def remember_post(self, packet: PacketV4) -> None:
        """Capture the post as the transport template + routing envelope (for seq)"""
        self._post_template = packet
        self._envelope_template = packet.payload[
            self._SERIAL_FRAGMENT_LEN : self.HEADER_LEN
        ]

    def _next_seq(self) -> int:
        # Track the panel's session seq from the latest post, else a local counter.
        if self._envelope_template is not None and len(self._envelope_template) > 5:
            return self._envelope_template[5]
        self._write_seq = (self._write_seq + 1) & 0xFF
        return self._write_seq

    def write_packet(self, config_bytes: bytes) -> Packet | PacketV4:
        """Build the control-write frame for a serialized `ConfigWrite`"""
        if self._post_template is None:
            # No telemetry post captured yet: plain v3 fallback.
            return Packet(0x21, 0x60, 0xFE, 0x11, config_bytes, 0x01, 0x01, 0x13)
        envelope = (
            self._WRITE_ENVELOPE_PREFIX
            + bytes([self._next_seq()])
            + self._WRITE_ENVELOPE_MID
            + self._WRITE_ENVELOPE_SUFFIX
        )
        serial9 = self._serial[-self._SERIAL_FRAGMENT_LEN :].encode("ascii")
        serial16 = self._serial.encode("ascii")
        payload = serial9 + serial16 + envelope + config_bytes
        return dataclasses.replace(
            self._post_template,
            cmd_flags=self._WRITE_CMD_FLAGS,
            is_ack=True,
            is_rw_cmd=False,
            payload=payload,
        )

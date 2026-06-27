"""EcoFlow Smart Home Panel 3 (HR62/HR63/HR6C).

The SHP3 uses a different telemetry protocol than the SHP2. Instead of the
pd303 protobuf messages (src=0x0B cmd_set=0x0C), it streams data on
src=0x32 cmd_set=0x40 cmd_id=0x30. Each payload is:

    [9 bytes ASCII serial fragment][13 byte envelope/seq header][protobuf]

Everything is keyed to PHYSICAL SLOT number (the breaker position, 1-32):
  - config messages carry a circuit name string (sub-field 5); the message's
    own protobuf field number encodes the physical slot:
      fields 794-805 -> slots 1-12,  fields 920-939 -> slots 13-32.
    (The internal channel index in sub-field 7 is NOT the physical slot and is
    ignored.)
  - field 1014 + S : live data for physical slot S (f1=voltage V, f2=power W
                     [signed, negative = consumption], f3=current A)
  - field 956/957  : grid voltage L1 / L2

Circuit entity index = physical slot number, so HA matches the panel labels.
240V breakers occupy two adjacent slots and appear under both (e.g. A/C on
slots 2 & 4). Verified against a real panel: slot 27 = microwave (1700W spike).

Control writes (circuit on/off, energy settings, Storm Guard, Charge Now) are
standard-protocol PROPERTY_WRITE frames carrying a ConfigWrite protobuf; see
_send_config_write for the transport (captured from the EcoFlow app via Frida).
"""

import dataclasses
import struct

from ..devicebase import AdvertisementData, BLEDevice, DeviceBase
from ..entity import controls
from ..packet import Packet, PacketV4
from ..props import Field, UpdatableProps, field_group
from ..props.enums import IntFieldValue


class OperatingMode(IntFieldValue):
    """SHP3 energy-strategy operating mode (CfgEnergyStrategyOperateMode subfields)."""

    UNKNOWN = -1
    NONE = 0           # "Backup": no operating mode selected (eps may still be on)
    SELF_POWERED = 1   # operate_self_powered_open
    SCHEDULED = 2      # operate_scheduled_open
    INTELLIGENT = 6    # operate_intelligent_schedule_mode_open
    # NB: subfield 4 (operate_eps_mode) and 5 (operate_mix_scheduled_open) are NOT
    # operating modes. eps is the independent fast-cutover toggle (Backup Power
    # Settings); it must be preserved, never overwritten, when setting the mode.


class CircuitStatus(IntFieldValue):
    """Per-circuit relay status from LoadChSta.load_sta (LOAD_CH_STA).

    This is the panel's authoritative on/off state for a breaker position. The
    OFF (0) default is omitted on the wire, so a circuit that is off arrives with
    no load_sta sub-field (parsed below as OFF).
    """

    UNKNOWN = -1     # LOAD_CH_UNKNOWN_STA (4) and any unrecognised value
    OFF = 0          # LOAD_CH_POWER_OFF — relay open / circuit off
    ON_GRID = 1      # LOAD_CH_POWER_ON_GRID — on, powered from grid
    ON_BACK = 2      # LOAD_CH_POWER_ON_BACK — on, powered from battery backup
    EM_STOP = 3      # LOAD_CH_EM_STOP — emergency stop

NUM_OF_CIRCUITS = 32

# Live data for physical slot S is at protobuf field (1014 + S).
_CIRCUIT_LIVE_BASE = 1014
_GRID_VOLTAGE_L1 = 956
_GRID_VOLTAGE_L2 = 957

# A 240V (split-phase) circuit occupies two breaker slots on opposite legs. In the
# panel's slot numbering the two poles of one two-pole breaker sit two positions
# apart in the same column (e.g. A/C on slots 2 & 4, Sub Panel on slots 8 & 10), and
# the panel reports the SAME circuit name on both slots. We detect a pair as two
# identically-named slots exactly this far apart, and gang their relays so they
# always switch together (switching only one leg leaves the load half-energized —
# one leg still live at the appliance — which is a shock hazard and can damage
# split-phase equipment).
_CIRCUIT_PAIR_SLOT_GAP = 2

_HEADER_LEN = 22  # 9 ASCII + 13 binary envelope before the protobuf body
_SERIAL_LEN = 9   # ASCII serial fragment at the start of every payload
_ENVELOPE_LEN = 13  # standard-protocol routing envelope after the serial

# Standard-protocol routing. A control write is a PROPERTY_WRITE (0x11) carrying a
# ConfigWrite protobuf. Telemetry posts use PROPERTY_POST_UI (0x15).
_ENVELOPE_CMD_ID_OFFSET = 7   # cmd-id index in the INCOMING post envelope (telemetry/ack)
_PROPERTY_WRITE = 0x11        # StandProtocolCmdId.PROPERTY_WRITE (17)
_PROPERTY_WRITE_ACK = 0x12    # StandProtocolCmdId.PROPERTY_WRITE_ACK (18)

# ConfigWrite carries per-channel control at field (386 + channel); each is a
# LoadChCtrlSet whose field 1 = chanel_enable_ctrl. The app sends ONLY field 1 (no
# ctrl_mode).
_CONFIG_WRITE_CH_BASE = 386
# chanel_enable_ctrl command codes, confirmed against a live circuit: ON=1, OFF=2
# (0 is a no-op on this panel).
_CIRCUIT_STATE_ON = 1
_CIRCUIT_STATE_OFF = 2
_PROPERTY_POST_UI = 0x15  # normal telemetry post envelope cmd-id

# EXACT outbound control-write framing, captured from the EcoFlow app via Frida
# (2026-06-05). Build the V4 frame by mirroring the panel's incoming post header but
# with cmd_flags = 0x10 (the app's outbound value; posts use 0x20), is_ack=True,
# is_rw=False. Payload = serial9 + FULL serial16 + envelope + ConfigWrite, where the
# 11-byte envelope is:  40 03 03 <seq> FE 11 00 21 01 0B 01
_WRITE_CMD_FLAGS = 0x10
_WRITE_ENVELOPE_PREFIX = bytes([0x40, 0x03, 0x03])              # before the seq byte
_WRITE_ENVELOPE_MID = bytes([0xFE, _PROPERTY_WRITE, 0x00])      # cmd_set, cmd_id, 0x00
_WRITE_ENVELOPE_SUFFIX = bytes([0x21, 0x01, 0x0B, 0x01])

# Energy-system ConfigWrite controls. When a battery (DPU X) is bonded to the SHP3
# the panel is the authority for these (the DPU X's own controls are disabled), so
# they live here. Each is (write = ConfigWrite field, read = DisplayPropertyUpload
# field number parsed from telemetry for the entity's current value).
_BACKUP_RESERVE_WRITE_FIELD = 102   # cfg_backup_reverse_soc
_BACKUP_RESERVE_READ_FIELD = 461    # backup_reverse_soc
_CHARGE_LIMIT_WRITE_FIELD = 33      # cfg_max_chg_soc
_CHARGE_LIMIT_READ_FIELD = 270      # cms_max_chg_soc
_AC_CHARGING_WRITE_FIELD = 542      # cfg_panel_max_charge_pow_set (panel, not battery 246)
_AC_CHARGING_READ_FIELD = 1244      # panel_max_charge_pow_set

# Operating mode is a sub-message (one bool per mode). The SHP3 is a panel, so the
# write targets the panel-specific cfg field (544); flip to 106 if it has no effect.
# self_powered=1, scheduled=2, tou=3 are identical subfields in both variants.
_OPERATING_MODE_WRITE_FIELD = 544        # cfg_panle_energy_strategy_operate_mode
_OPERATING_MODE_READ_FIELD = 393         # energy_strategy_operate_mode
_OPERATING_MODE_PANEL_READ_FIELD = 1245  # panle_energy_strategy_operate_mode

# EPS fast-cutover (Backup Power Settings) is subfield 4 of the operating-mode message;
# it has no working dedicated write field on this panel, so it is not exposed as a
# control. It is still parsed (into _eps_mode_on) so operating-mode writes preserve it.

# Storm Guard: charge the battery to full ahead of a forecast storm.
_STORM_GUARD_WRITE_FIELD = 93      # cfg_storm_pattern (CfgStormPattern submessage)
_STORM_GUARD_READ_FIELD = 467      # storm_pattern_enable (bool)

# "Charge Now" (Smart Inlet Box page): force-charge the battery from grid. This is a
# PANEL backup-channel control, NOT the battery's cfg_grid_charge_to_battery_enable
# (603) — the panel silently drops 603 and never reports its read field (1686).
#   cfg_panel_backup_ch{N}_ctrl = 534 + N  (ch1 = 535); BackupCtrl.ctrl_force_chg = sub 2
#   panel_backup_ch{N}_Info     = 1223 + N (read; tells us which channel is the battery)
_BACKUP_CH_CTRL_BASE = 534         # cfg_panel_backup_ch{N}_ctrl
_BACKUP_CH_INFO_BASE = 1223        # panel_backup_ch{N}_Info
_BACKUP_CTRL_FORCE_CHG = 2         # BackupCtrl.ctrl_force_chg subfield
_BACK_CH_TYPE_BAT = 1              # BACK_CH_TYPE.BACK_CH_TYPE_BAT (battery channel)
# Force-charge command codes. Like the circuit chanel_enable_ctrl on this panel, 0 is a
# no-op; ON=1 turned force-charge on (verified), OFF=2 stops it (0 did nothing).
_FORCE_CHG_ON = 1
_FORCE_CHG_OFF = 2

# Seconds between keep-alive heartbeats while authenticated. Short enough to
# stay under the panel's idle-link timeout, long enough to stay quiet.
_KEEPALIVE_INTERVAL = 20


def _pb_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        out.append(b | 0x80 if value else b)
        if not value:
            return bytes(out)


def _pb_varint_field(field: int, value: int) -> bytes:
    return _pb_varint(field << 3) + _pb_varint(value)


def _pb_message_field(field: int, data: bytes) -> bytes:
    return _pb_varint((field << 3) | 2) + _pb_varint(len(data)) + data


def _encode_config_write_ctrl(channel: int, state: int) -> bytes:
    """Serialize ConfigWrite{ cfg_load_ch{channel}_ctrl_info: {chanel_enable_ctrl: state} }.

    The app sends only field 1 (chanel_enable_ctrl); no ctrl_mode (field 2).
    """
    load_ch_ctrl = _pb_varint_field(1, state)  # chanel_enable_ctrl
    return _pb_message_field(_CONFIG_WRITE_CH_BASE + channel, load_ch_ctrl)


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
    raise IndexError("truncated varint")


def _walk(data: bytes) -> list[tuple[int, int, object]]:
    """Walk a protobuf message, returning (field_number, wire_type, value).

    value is float for wire type 5, int for varint, bytes for length-delimited.
    """
    out: list[tuple[int, int, object]] = []
    pos = 0
    n = len(data)
    while pos < n:
        try:
            tag, pos = _read_varint(data, pos)
        except IndexError:
            break
        field = tag >> 3
        wire = tag & 7
        if wire == 0:  # varint
            try:
                val, pos = _read_varint(data, pos)
            except IndexError:
                break
            out.append((field, wire, val))
        elif wire == 5:  # 32-bit (float)
            if pos + 4 > n:
                break
            out.append((field, wire, struct.unpack_from("<f", data, pos)[0]))
            pos += 4
        elif wire == 1:  # 64-bit
            if pos + 8 > n:
                break
            out.append((field, wire, struct.unpack_from("<d", data, pos)[0]))
            pos += 8
        elif wire == 2:  # length-delimited
            try:
                ln, pos = _read_varint(data, pos)
            except IndexError:
                break
            if pos + ln > n:
                break
            out.append((field, wire, data[pos : pos + ln]))
            pos += ln
        else:
            break
    return out


class Device(DeviceBase, UpdatableProps):
    """Smart Home Panel 3"""

    SN_PREFIX = (b"HR62", b"HR63", b"HR6C")
    NAME_PREFIX = "EF-HR6"

    NUM_OF_CIRCUITS = NUM_OF_CIRCUITS

    # Per-circuit telemetry (1-based). Keys match descriptions registered in sensor.py.
    circuit_power = field_group(
        lambda n: Field[float](),
        count=NUM_OF_CIRCUITS,
        name_template="shp3_circuit_power_{n}",
    )
    circuit_voltage = field_group(
        lambda n: Field[float](),
        count=NUM_OF_CIRCUITS,
        name_template="shp3_circuit_voltage_{n}",
    )
    circuit_current = field_group(
        lambda n: Field[float](),
        count=NUM_OF_CIRCUITS,
        name_template="shp3_circuit_current_{n}",
    )
    circuit_name = field_group(
        lambda n: Field[str](),
        count=NUM_OF_CIRCUITS,
        name_template="shp3_circuit_name_{n}",
    )
    # Per-circuit relay state (from the config message's "enabled" sub-field).
    # Drives the on/off switch entities and their availability. Default to off
    # when unreported: the panel omits the enabled sub-field for an off circuit
    # (proto omits false/zero values), which would otherwise leave the field None
    # and grey out the switch. Missing => off, so the toggle stays live.
    circuit_enabled = field_group(
        lambda n: Field[bool]().default_when_missing(False),
        count=NUM_OF_CIRCUITS,
        name_template="shp3_circuit_enabled_{n}",
    )
    # Per-circuit relay status (the primary on/off depiction): Off / On (Grid) /
    # On (Backup) / Emergency Stop, from LoadChSta.load_sta. The switch above
    # remains for control; this enum sensor is what shows the real panel state.
    circuit_status = field_group(
        lambda n: Field[CircuitStatus]().default_when_missing(CircuitStatus.OFF),
        count=NUM_OF_CIRCUITS,
        name_template="shp3_circuit_status_{n}",
    )

    grid_voltage_l1 = Field[float]()
    grid_voltage_l2 = Field[float]()
    total_power = Field[float]()

    # Energy-system settings (current values from telemetry; controls below).
    backup_reserve_level = Field[int]()
    backup_charge_limit = Field[int]()
    ac_charging = Field[int]()
    operating_mode_select = Field[OperatingMode]()
    # Default to off when the panel hasn't reported the field yet, so the switch is
    # available (not greyed out) instead of stuck unknown. Charge Now's read field
    # (grid_charge_to_battery_enable) in particular is not always emitted.
    charge_now = Field[bool]().default_when_missing(False)
    storm_guard = Field[bool]().default_when_missing(False)

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return any(sn.startswith(prefix) for prefix in cls.SN_PREFIX)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        # Lazily import here to avoid any import-order issues in the eflib package.
        from ..commands import TimeCommands

        self._time_commands = TimeCommands(self)
        # Latest known power per circuit, for computing total_power.
        self._circuit_power_cache: dict[int, float] = {}

        # Control-write state. Outbound writes reuse the latest telemetry post's V4
        # transport header (src/dst/obfuscation), with a freshly built payload.
        self._full_sn = sn
        self._post_template: PacketV4 | None = None
        self._serial_fragment: bytes | None = None
        self._envelope_template: bytes | None = None
        self._write_seq = 0x20
        # Physical breaker slot -> device-internal load channel (config sub-field 7).
        self._slot_to_channel: dict[int, int] = {}
        # Latest circuit name per slot, and the derived 240V slot pairing
        # (slot -> partner slot) used to gang two-pole breakers together.
        self._circuit_names: dict[int, str] = {}
        self._circuit_pairs: dict[int, int] = {}
        # Which panel backup channel (1-3) holds the battery, for Charge Now force-charge.
        self._battery_backup_channel: int | None = None
        # The app registers its user id (cmd_set=0x35 cmd_id=0xA8) after auth; without
        # it the panel streams telemetry but rejects control writes. Send once.
        self._userid_sent = False

        # The SHP3 streams telemetry one-directionally and will throttle (lag) or
        # tear down (drop) a link it considers idle, since the host otherwise
        # never sends anything after the initial time sync. Re-send the RTC
        # response on a timer as an application-level heartbeat to keep the link
        # warm. The timer only runs while AUTHENTICATED (see DeviceBase).
        self.add_timer_task(self._send_keepalive, interval=_KEEPALIVE_INTERVAL)

    async def _send_keepalive(self) -> None:
        """Periodic heartbeat: re-send the RTC response the panel asks for."""
        await self._time_commands.sendRTCCheck()

    async def _send_userid_registration(self) -> None:
        """Register our user id with the panel so it accepts control writes.

        Mirrors the app's post-auth frame (captured via Frida):
          Packet(src=0x21, dst=0x35, cmd_set=0x35, cmd_id=0xA8,
                 payload = 0x01 + user_id ascii, zero-padded to 69 bytes).
        """
        user_id = getattr(self._conn, "_user_id", "") or ""
        payload = bytes([0x01]) + user_id.encode("ascii")
        if len(payload) < 69:
            payload += bytes(69 - len(payload))
        packet = Packet(0x21, 0x35, 0x35, 0xA8, payload, 0x01, 0x01, 0x03)
        self._logger.debug("SHP3 sending userid registration (cmd_id=0xA8)")
        await self._conn.sendPacket(packet)

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        self.reset_updated()

        if packet.src == 0x32 and packet.cmd_set == 0x40 and packet.cmd_id == 0x30:
            # Capture this post as the template for outbound control writes.
            if isinstance(packet, PacketV4):
                self._post_template = packet
            self._parse_telemetry(packet.payload)
            # Log standard-protocol write acks so we can confirm control commands.
            # The std-protocol cmd-id is the byte after 0xFE (handles both the post
            # layout 9+13 and the ack layout 9 + full-serial + envelope).
            fe_idx = packet.payload.find(0xFE, _SERIAL_LEN)
            if fe_idx != -1 and fe_idx + 1 < len(packet.payload):
                env_cmd_id = packet.payload[fe_idx + 1]
                # 0x15/0x16/0x19 = normal telemetry posts; anything else is an
                # ack/reply/error worth seeing (0x12 = PROPERTY_WRITE_ACK).
                if env_cmd_id == _PROPERTY_WRITE_ACK:
                    self._logger.debug(
                        "SHP3 PROPERTY_WRITE_ACK %s",
                        self._decode_write_ack(packet.payload, fe_idx),
                    )
                elif env_cmd_id not in (0x15, 0x16, 0x19):
                    self._logger.debug(
                        "SHP3 panel response env_cmd_id=0x%02x: %s",
                        env_cmd_id, packet.payload.hex(),
                    )
            processed = True

        elif (
            packet.src == 0x35
            and packet.cmd_set == 0x01
            and packet.cmd_id == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            # SHP3 requests time right after auth; responding triggers the
            # telemetry stream (src=0x32 cmd_set=0x40).
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
                if not self._userid_sent:
                    self._userid_sent = True
                    self._conn._add_task(self._send_userid_registration())
            processed = True

        elif packet.src == 0x35 and packet.cmd_set == 0x35 and packet.cmd_id == 0x20:
            # Periodic liveness ping from the panel. Echo it back so the panel
            # knows the BLE client is still present and keeps streaming
            # telemetry (an unanswered ping makes it throttle / drop the link).
            await self._conn.replyPacket(packet)
            processed = True

        for field_name in self.updated_fields:
            try:
                self.update_callback(field_name)
                self.update_state(field_name, getattr(self, field_name))
            except Exception as e:  # noqa: BLE001
                self._logger.warning(
                    "Error updating field %s: %s", field_name, e
                )

        return processed

    def _parse_telemetry(self, payload: bytes) -> None:
        if len(payload) <= _HEADER_LEN:
            return
        # Capture the panel's own serial fragment + routing envelope to mirror
        # them on outbound control writes.
        self._serial_fragment = payload[:_SERIAL_LEN]
        self._envelope_template = payload[_SERIAL_LEN:_HEADER_LEN]
        body = payload[_HEADER_LEN:]

        for field_num, wire, value in _walk(body):
            if wire == 2 and isinstance(value, bytes):
                if field_num in (
                    _OPERATING_MODE_READ_FIELD,
                    _OPERATING_MODE_PANEL_READ_FIELD,
                ):
                    self._parse_operating_mode(field_num, value)
                elif _BACKUP_CH_INFO_BASE < field_num <= _BACKUP_CH_INFO_BASE + 3:
                    self._parse_backup_ch_info(field_num - _BACKUP_CH_INFO_BASE, value)
                else:
                    self._parse_circuit_message(field_num, value)
            elif wire == 5:
                if field_num == _GRID_VOLTAGE_L1:
                    self.grid_voltage_l1 = round(value, 2)
                elif field_num == _GRID_VOLTAGE_L2:
                    self.grid_voltage_l2 = round(value, 2)
            elif wire == 0:
                if field_num == _BACKUP_RESERVE_READ_FIELD:
                    self.backup_reserve_level = value
                elif field_num == _CHARGE_LIMIT_READ_FIELD:
                    self.backup_charge_limit = value
                elif field_num == _AC_CHARGING_READ_FIELD:
                    self.ac_charging = value
                elif field_num == _STORM_GUARD_READ_FIELD:
                    self.storm_guard = bool(value)

        # Total household consumption = sum of all known circuit powers.
        if self._circuit_power_cache:
            self.total_power = round(sum(self._circuit_power_cache.values()), 1)

    def _parse_backup_ch_info(self, channel: int, data: bytes) -> None:
        """Identify which backup channel (1-3) holds the battery, for Charge Now.

        BackupChInfo.ch_dev_type (sub 2) == BACK_CH_TYPE_BAT marks the battery channel;
        Charge Now force-charges that channel.
        """
        fields = {f: v for f, w, v in _walk(data) if w == 0}
        if fields.get(2) == _BACK_CH_TYPE_BAT and self._battery_backup_channel != channel:
            self._battery_backup_channel = channel
            self._logger.debug("SHP3 battery backup channel = %s", channel)

    @staticmethod
    def _config_field_to_slot(field_num: int) -> int | None:
        """Map a config message's protobuf field number to a physical slot.

        Verified against the physical panel: the config name's field number
        encodes the breaker position, in two blocks.
          fields 794-805 -> slots 1-12   (slot = field - 793)
          fields 920-939 -> slots 13-32  (slot = field - 907)
        (The internal channel index in sub-field 7 is NOT the physical slot.)
        """
        if 794 <= field_num <= 805:
            return field_num - 793
        if 920 <= field_num <= 939:
            return field_num - 907
        return None

    def _recompute_circuit_pairs(self) -> None:
        """Derive 240V slot pairings (slot -> partner slot) from circuit names.

        A two-pole 240V breaker is reported under the SAME name on two slots that
        sit _CIRCUIT_PAIR_SLOT_GAP positions apart (opposite legs, same column).
        We pair exactly those: a name on precisely two slots that are that far
        apart. Names appearing on a different count or spacing are left unpaired
        (ambiguous), so a stray duplicate name never silently gangs unrelated
        circuits. See set_circuit_power for why both poles must switch together.
        """
        slots_by_name: dict[str, list[int]] = {}
        for slot, name in self._circuit_names.items():
            if name:
                slots_by_name.setdefault(name, []).append(slot)

        pairs: dict[int, int] = {}
        for slots in slots_by_name.values():
            if len(slots) != 2:
                continue
            low, high = sorted(slots)
            if high - low == _CIRCUIT_PAIR_SLOT_GAP:
                pairs[low] = high
                pairs[high] = low

        if pairs != self._circuit_pairs:
            self._circuit_pairs = pairs
            self._logger.debug("SHP3 240V circuit pairs (slot->partner): %s", pairs)

    def _parse_circuit_message(self, field_num: int, value: bytes) -> None:
        """Parse a sub-message that is either a circuit config or live data.

        - Config messages carry a name string (sub-field 5); the message's own
          protobuf field number encodes the physical slot (see
          _config_field_to_slot).
        - Live messages carry only float sub-fields (1=voltage, 2=power,
          3=current) and live at field number 1014 + physical slot.
        """
        name = None
        voltage = power = current = None
        load_sta = None
        channel = None
        for sfn, sw, sv in _walk(value):
            if sfn == 5 and sw == 2 and isinstance(sv, bytes):
                try:
                    name = sv.decode("utf-8")
                except UnicodeDecodeError:
                    name = None
            elif sfn == 1 and sw == 0:
                # Status message (LoadChSta): sub-field 1 is load_sta (LOAD_CH_STA):
                # 0=OFF, 1=ON via grid, 2=ON via backup, 3=emergency stop, 4=unknown.
                # The OFF(0) default is omitted on the wire, so an off circuit arrives
                # with no sub-field 1 (handled below as load_sta=0 => off).
                load_sta = sv
            elif sfn == 7 and sw == 2 and isinstance(sv, bytes):
                # Config message: sub-field 7 carries the device-internal load
                # channel index in its own sub-field 1.
                for ifn, iw, iv in _walk(sv):
                    if ifn == 1:
                        channel = iv
            elif sw == 5:
                if sfn == 1:
                    voltage = round(sv, 2)
                elif sfn == 2:
                    power = sv
                elif sfn == 3:
                    current = round(sv, 3)

        # Config message: map the circuit name to its physical slot via the
        # protobuf field number.
        if name:
            slot = self._config_field_to_slot(field_num)
            if slot is not None and 1 <= slot <= NUM_OF_CIRCUITS:
                setattr(self, f"shp3_circuit_name_{slot}", name)
                # Track names to derive 240V slot pairings; only recompute when a
                # name actually changes (names are re-reported every post).
                if self._circuit_names.get(slot) != name:
                    self._circuit_names[slot] = name
                    self._recompute_circuit_pairs()
                # Authoritative on/off: a parsed status message with load_sta
                # omitted (None) means OFF (0). ON = grid (1) or backup (2);
                # emergency-stop (3) / unknown (4) are treated as not-on.
                setattr(
                    self,
                    f"shp3_circuit_enabled_{slot}",
                    (load_sta or 0) in (1, 2),
                )
                # Richer status enum (Off / On Grid / On Backup / E-Stop) — the
                # primary depiction shown in HA.
                setattr(
                    self,
                    f"shp3_circuit_status_{slot}",
                    CircuitStatus.from_value(load_sta or 0),
                )
                if channel is not None:
                    self._slot_to_channel[slot] = channel
            return

        # Live data message: slot = field number - live base.
        if _CIRCUIT_LIVE_BASE < field_num <= _CIRCUIT_LIVE_BASE + NUM_OF_CIRCUITS:
            slot = field_num - _CIRCUIT_LIVE_BASE
            if voltage is not None:
                setattr(self, f"shp3_circuit_voltage_{slot}", voltage)
            # Device reports consumption as negative; flip so consumption is positive.
            power_w = round(-power, 1) if power is not None else 0.0
            setattr(self, f"shp3_circuit_power_{slot}", power_w)
            setattr(
                self,
                f"shp3_circuit_current_{slot}",
                current if current is not None else 0.0,
            )
            self._circuit_power_cache[slot] = power_w

    @controls.for_each(
        circuit_enabled,
        control=controls.outlet,
        translation_key="circuit_is_enabled",
        translation_placeholders=lambda i: {"circuit": str(i)},
    )
    async def set_circuit_power(self, circuit_id: int, enable: bool) -> None:
        """Turn a circuit on/off via a standard-protocol PROPERTY_WRITE.

        circuit_id is the 1-based physical slot. For a 240V (split-phase) circuit
        the breaker occupies two slots on opposite legs; both relays MUST switch
        together — opening only one leaves the load half-energized (one leg still
        live at the appliance), a shock hazard that can also damage split-phase
        equipment. When circuit_id is part of a detected 240V pair we drive both
        slots, so toggling either of the two switch entities moves the whole circuit.
        """
        slots = [circuit_id]
        partner = self._circuit_pairs.get(circuit_id)
        if partner is not None and partner != circuit_id:
            slots.append(partner)
            self._logger.debug(
                "SHP3 ganged 240V circuit: slot %s -> also slot %s",
                circuit_id, partner,
            )
        for slot in slots:
            await self._write_circuit_state(slot, enable)

    async def _write_circuit_state(self, slot: int, enable: bool) -> None:
        """Write one slot's relay state and optimistically update its switch.

        The frame matches exactly what the EcoFlow app sends (captured via Frida):
        the V4 transport header is the panel's own incoming-post header (so
        addressing/obfuscation match), with cmd_flags forced to the app's outbound
        value and a freshly built payload. The panel's protobuf is keyed by physical
        slot everywhere (config field numbers, live data 1014+slot), so cfg_load_ch{N}
        uses the physical slot as the channel: field = 386 + slot. (The telemetry
        sub-field 7 "internal channel" is NOT it.)
        """
        channel = slot
        state = _CIRCUIT_STATE_ON if enable else _CIRCUIT_STATE_OFF
        if not await self._send_config_write(_encode_config_write_ctrl(channel, state)):
            return
        self._logger.debug(
            "SHP3 set_circuit_power slot=%s channel=%s enable=%s state=%s",
            slot, channel, enable, state,
        )
        # Optimistically reflect the command in the switch state so the UI updates
        # immediately (telemetry will correct it if the write didn't take).
        try:
            field_name = f"shp3_circuit_enabled_{slot}"
            setattr(self, field_name, enable)
            self.update_state(field_name, enable)
        except Exception:  # noqa: BLE001
            pass

    async def _send_config_write(self, config_write: bytes) -> bool:
        """Send a ConfigWrite to the panel via the standard-protocol PROPERTY_WRITE.

        The V4 transport header mirrors the panel's latest incoming post (so
        addressing/obfuscation match), with cmd_flags forced to the app's outbound
        value; only the payload changes. Returns True if the frame was sent.
        """
        if self._post_template is None:
            self._logger.warning(
                "SHP3 config write skipped: no telemetry post captured yet"
            )
            return False

        # Sync the envelope seq to the panel's current session sequence (the byte
        # after "40 03 03" in the latest post envelope); fall back to a local counter.
        if self._envelope_template is not None and len(self._envelope_template) > 5:
            seq = self._envelope_template[5]
        else:
            self._write_seq = (self._write_seq + 1) & 0xFF
            seq = self._write_seq
        envelope = (
            _WRITE_ENVELOPE_PREFIX
            + bytes([seq])
            + _WRITE_ENVELOPE_MID
            + _WRITE_ENVELOPE_SUFFIX
        )
        serial9 = self._full_sn[-9:].encode("ascii")
        serial16 = self._full_sn.encode("ascii")
        payload = serial9 + serial16 + envelope + config_write
        packet = dataclasses.replace(
            self._post_template,
            cmd_flags=_WRITE_CMD_FLAGS,
            is_ack=True,
            is_rw_cmd=False,
            payload=payload,
        )
        self._logger.debug("SHP3 sending ConfigWrite=%s", config_write.hex())
        await self._conn.sendPacket(packet)
        return True

    def _decode_write_ack(self, payload: bytes, fe_idx: int) -> str:
        """Decode a PROPERTY_WRITE_ACK body for debug logging.

        Ack layout: serial9 + serial16 + envelope(40 03 03 <seq> FE 12 00 0B 01 21 01)
        + protobuf {1: acked ConfigWrite field number, 2: result}. The 0xFE-prefixed
        envelope is 7 bytes, so the ack protobuf starts at fe_idx + 7.
        """
        body = payload[fe_idx + 7 :]
        fields = {f: v for f, w, v in _walk(body) if w == 0}
        return (
            f"acked_cfg_field={fields.get(1)} result={fields.get(2)} "
            f"body={body.hex()}"
        )

    def _optimistic(self, field_name: str, value: object) -> None:
        """Reflect a just-sent value in the entity immediately (telemetry corrects it)."""
        try:
            setattr(self, field_name, value)
            self.update_state(field_name, value)
        except Exception:  # noqa: BLE001
            pass

    async def _set_uint_config(
        self, write_field: int, read_field_name: str, value: int
    ) -> bool:
        sent = await self._send_config_write(_pb_varint_field(write_field, value))
        if sent:
            self._optimistic(read_field_name, value)
        return sent

    @controls.battery(backup_reserve_level, min=0, max=100)
    async def set_backup_reserve_level(self, value: float) -> bool:
        """Set the battery backup-reserve SOC (%). The panel relays it to the battery."""
        soc = max(0, min(100, int(value)))
        return await self._set_uint_config(
            _BACKUP_RESERVE_WRITE_FIELD, "backup_reserve_level", soc
        )

    @controls.battery(backup_charge_limit, min=80, max=100)
    async def set_backup_charge_limit(self, value: float) -> bool:
        """Set the battery max-charge SOC limit (%)."""
        soc = max(80, min(100, int(value)))
        return await self._set_uint_config(
            _CHARGE_LIMIT_WRITE_FIELD, "backup_charge_limit", soc
        )

    @controls.power(ac_charging, min=600, max=12000, step=100)
    async def set_ac_charging(self, value: float) -> bool:
        """Set the AC charging power (W), rounded to the nearest 100."""
        watts = max(600, min(12000, int(value) // 100 * 100))
        return await self._set_uint_config(
            _AC_CHARGING_WRITE_FIELD, "ac_charging", watts
        )

    def _parse_operating_mode(self, field_num: int, data: bytes) -> None:
        """Read the active mode from a CfgPanelEnergyStrategyOperateMode sub-message.

        Mode is whichever of subfields 1 (self-powered) / 2 (scheduled) / 6
        (intelligent) is set; none set == "Backup". Subfields 4 (eps) and 5 (mix)
        are independent flags, captured here only so set_operating_mode can preserve
        them. The generic field (393) is empty on this panel and skipped.
        """
        subs = [f for f, w, v in _walk(data) if w == 0 and v]
        if not subs:
            return  # empty message (e.g. the unused generic field 393): don't clobber
        mode = OperatingMode.NONE  # no mode bit set == "Backup"
        eps = mix = False
        for sub_field in subs:
            if sub_field == 4:
                eps = True
            elif sub_field == 5:
                mix = True
            elif sub_field == 1:
                mode = OperatingMode.SELF_POWERED
            elif sub_field == 2:
                mode = OperatingMode.SCHEDULED
            elif sub_field == 6:
                mode = OperatingMode.INTELLIGENT
        # Track eps/mix only so operating-mode writes preserve them (subfield 4/5);
        # EPS is not exposed as its own control.
        self._eps_mode_on = eps
        self._mix_scheduled_on = mix
        self.operating_mode_select = mode

    def _build_operating_mode_config(
        self, mode: OperatingMode, eps_on: bool, mix_on: bool
    ) -> bytes:
        """Serialize ConfigWrite{ cfg_panle_energy_strategy_operate_mode: {...} }.

        Reconstructs the panel's exact CfgPanelEnergyStrategyOperateMode bytes: set
        only the chosen mode bool (self=1 / scheduled=2 / intelligent=6, or none for
        "Backup") plus the independent eps(4)/mix(5) flags, in ascending field order.
        Confirmed against the panel's own reports (e.g. scheduled+eps == 10012001).
        Writes that used the wrong subfield or dropped the eps bit were ignored.
        """
        sub_message = bytearray()
        if mode == OperatingMode.SELF_POWERED:
            sub_message += _pb_varint_field(1, 1)
        if mode == OperatingMode.SCHEDULED:
            sub_message += _pb_varint_field(2, 1)
        if eps_on:
            sub_message += _pb_varint_field(4, 1)
        if mix_on:
            sub_message += _pb_varint_field(5, 1)
        if mode == OperatingMode.INTELLIGENT:
            sub_message += _pb_varint_field(6, 1)
        return _pb_message_field(_OPERATING_MODE_WRITE_FIELD, bytes(sub_message))

    @controls.select(operating_mode_select, options=OperatingMode)
    async def set_operating_mode(self, mode: OperatingMode) -> bool:
        """Set the energy-strategy operating mode via the panel."""
        if mode == OperatingMode.UNKNOWN:
            return False
        # Preserve the independent eps/mix flags at their current telemetry values.
        eps_on = getattr(self, "_eps_mode_on", False)
        mix_on = getattr(self, "_mix_scheduled_on", False)
        config_write = self._build_operating_mode_config(mode, eps_on, mix_on)
        sent = await self._send_config_write(config_write)
        if sent:
            self._optimistic("operating_mode_select", mode)
        return sent

    @controls.switch(charge_now)
    async def set_charge_now(self, enable: bool) -> None:
        """Charge Now: force-charge the battery from grid (panel backup channel).

        The battery's own cfg_grid_charge_to_battery_enable (603) is not accepted by the
        panel; force-charge targets the panel backup channel carrying the battery
        (learned from telemetry; defaults to channel 1 until identified). The command
        value is a code, not a bool: ON=1, OFF=2 (0 is a no-op on this panel).
        """
        channel = self._battery_backup_channel or 1
        state = _FORCE_CHG_ON if enable else _FORCE_CHG_OFF
        backup_ctrl = _pb_varint_field(_BACKUP_CTRL_FORCE_CHG, state)
        config_write = _pb_message_field(_BACKUP_CH_CTRL_BASE + channel, backup_ctrl)
        if await self._send_config_write(config_write):
            self._optimistic("charge_now", enable)

    @controls.switch(storm_guard)
    async def set_storm_guard(self, enable: bool) -> None:
        """Storm Guard: charge the battery to full ahead of a forecast storm."""
        # cfg_storm_pattern is a CfgStormPattern submessage; the user toggle is its
        # subfield 1 (storm_pattern_enable).
        sub_message = _pb_varint_field(1, 1 if enable else 0)
        config_write = _pb_message_field(_STORM_GUARD_WRITE_FIELD, sub_message)
        if await self._send_config_write(config_write):
            self._optimistic("storm_guard", enable)

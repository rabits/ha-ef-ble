"""EcoFlow River 2 Pro (R621).

This device uses the classic EcoFlow BLE packet framing (Packet.version=2) and
cmdSet/cmdId messages (not protobuf).

Implemented switches (from your captures / spreadsheet):
- AC Output ON/OFF   (dst=0x05, cmdSet=0x20, cmdId=0x42, payload: [01|00] ffffffff...)
- DC Output ON/OFF   (dst=0x05, cmdSet=0x20, cmdId=0x51, payload: [01|00])
- X-Boost ON/OFF     (dst=0x05, cmdSet=0x20, cmdId=0x42, payload: ff [01|00] ffffff...)
- AC Always On       (dst=0x02, cmdSet=0x20, cmdId=0x5F, payload: [01|00] 05)
- Backup Reserve     (dst=0x02, cmdSet=0x20, cmdId=0x5E, payload: [01|00] [reserve%] 0000)

Notes:
- Some switch states are available from heartbeat packets; for others we also
  emit optimistic updates via DeviceBase.update_state() after writes.
"""

from __future__ import annotations

import logging
import struct

from ..devicebase import DeviceBase
from ..model import (
    DirectBmsMDeltaHeartbeatPack,
    DirectEmsDeltaHeartbeatPack,
    Mr330MpptHeart,
    Mr330PdHeart,
)
from ..packet import Packet
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

_LOGGER = logging.getLogger(__name__)

# Raw-data mappers used by raw_field(...)
pb_pd = dataclass_attr_mapper(Mr330PdHeart)
pb_mppt = dataclass_attr_mapper(Mr330MpptHeart)
pb_ems = dataclass_attr_mapper(DirectEmsDeltaHeartbeatPack)
pb_bms = dataclass_attr_mapper(DirectBmsMDeltaHeartbeatPack)


def _normalize_watts(v: int | None) -> int | None:
    """Normalize watt values.

    River heartbeats sometimes contain signed values for power rails.
    For HA power sensors we clamp negatives to 0.
    """

    if v is None:
        return None
    try:
        iv = int(v)
    except Exception:
        return None
    return 0 if iv < 0 else iv


def _sum_ints(*vals: int | None) -> int | None:
    total = 0
    seen = False
    for v in vals:
        if v is None:
            continue
        try:
            total += int(v)
            seen = True
        except Exception:
            continue
    return total if seen else None


def _clamp_nonneg(v: int | None) -> int | None:
    if v is None:
        return None
    try:
        iv = int(v)
    except Exception:
        return None
    return 0 if iv < 0 else iv


def _u16le(buf: bytes, offset: int) -> int | None:
    """Read little-endian u16 from buf at offset, or None if out of range."""
    if offset < 0 or offset + 1 >= len(buf):
        return None
    return buf[offset] | (buf[offset + 1] << 8)

def _remain_time_to_minutes(v: int | None) -> int | None:
    """Normalize remain_time to minutes.

    River firmware variants report remain_time either as minutes or as seconds.
    Heuristic: values > 2000 are treated as seconds.
    """
    if v is None:
        return None
    try:
        iv = int(v)
    except Exception:
        return None
    if iv < 0:
        return None
    return iv // 60 if iv > 2000 else iv


class Device(DeviceBase, RawDataProps):
    """EcoFlow River 2 Pro."""

    NAME_PREFIX = "EF-R62"
    SN_PREFIX = (b"R621",)

    # -----------------
    # Switch properties
    # -----------------
    # These are read by HA via SwitchEntityDescription.key

    # AC output enable state (heartbeat)
    ac_ports = raw_field(pb_pd.cfg_ac_enabled, lambda x: x == 1)

    # DC (car) output enable state (heartbeat)
    dc_12v_port = raw_field(pb_mppt.car_state, lambda x: x == 1)

    # X-Boost state (heartbeat)
    ac_xboost = raw_field(pb_mppt.cfg_ac_xboost, lambda x: x == 1)

    # "AC Always On" state (often present in PD heartbeat). If not present from
    # your firmware, the entity will still update optimistically after writes.
    ac_always_on = raw_field(pb_pd.ac_auto_on, lambda x: x == 1)

    # Backup reserve (UPS flag). If not present from your firmware, the entity
    # will still update optimistically after writes.
    energy_backup = raw_field(pb_ems.open_ups_flag, lambda x: x == 1)

    # Reserve level (percent)
    energy_backup_battery_level = raw_field(pb_ems.open_oil_eb_soc)

    # Discharge/charge limits (percent)
    battery_charge_limit_min = raw_field(pb_ems.min_dsg_soc)
    battery_charge_limit_max = raw_field(pb_ems.max_charge_soc)

    # -----------------
    # Telemetry sensors (heartbeat)
    # -----------------
    # Standard keys used by sensor.py (kept consistent with other devices).
    battery_level = raw_field(pb_pd.soc)
    battery_temperature = raw_field(pb_bms.temp)
    battery_time_remaining = raw_field(pb_pd.remain_time, _remain_time_to_minutes)

    input_power = raw_field(pb_pd.watts_in_sum)
    output_power = raw_field(pb_pd.watts_out_sum)

    # River 2 Pro note:
    # The protobuf/dataclass PD heartbeat mapping is sufficient for many config
    # fields, but the instantaneous power rails can drift/scale on some firmware
    # (you observed absurd kW readings). For R2P we therefore decode the power
    # rails from fixed offsets within the PD heartbeat payload (Packet v2,
    # src=0x02 cmdSet=0x20 cmdId=0x02), based on your plaintext captures.
    #
    # These are populated in data_parse().
    ac_input_power: int | None = None
    ac_output_power: int | None = None

    # The following are derived in data_parse() from decoded PD/MPPT heartbeats.
    # They are defined here so HA creates entities at setup time.
    dc_input_power: int | None = None
    solar_input_power: int | None = None
    car_input_power: int | None = None
    dc_output_power: int | None = None
    usbc_output_power: int | None = None
    usba_output_power: int | None = None

    # -----------------
    # Config/select/number properties (heartbeat)
    # -----------------
    # Car input current limit (mA): selectable 4A / 6A / 8A
    car_input_current_limit_ma = raw_field(pb_mppt.cfg_dc_chg_current)

    # DC input mode (0=Auto, 1=Solar, 2=Car)
    dc_mode = raw_field(pb_mppt.cfg_chg_type)

    # AC charging speed (W)
    ac_charge_speed_watts = raw_field(pb_mppt.cfg_chg_watts)

    # Standby / timeout controls
    device_timeout_minutes = raw_field(pb_pd.standby_min)
    lcd_timeout_seconds = raw_field(pb_pd.lcd_off_sec)
    ac_timeout_minutes = raw_field(pb_mppt.ac_standby_mins)

    def __init__(self, ble_dev, adv_data, sn: str) -> None:
        super().__init__(ble_dev, adv_data, sn)

        # Provide sensible defaults so entities show immediately.
        # (These will be overwritten by heartbeat values once parsed.)
        if self.car_input_current_limit_ma is None:
            self.car_input_current_limit_ma = 6000
        if self.dc_mode is None:
            self.dc_mode = 0
        if self.ac_charge_speed_watts is None:
            self.ac_charge_speed_watts = 500
        if self.battery_charge_limit_min is None:
            self.battery_charge_limit_min = 10
        if self.battery_charge_limit_max is None:
            self.battery_charge_limit_max = 90

    # -----------------
    # Device identity
    # -----------------

    @classmethod
    def check(cls, sn):
        # sn can be bytes or str depending on discovery path
        prefix = sn[:4] if isinstance(sn, (bytes, bytearray)) else str(sn)[:4].encode()
        return prefix in cls.SN_PREFIX

    @property
    def device(self):
        return "River 2 Pro"

    @property
    def packet_version(self):
        return 2

    # -----------------
    # Parsing
    # -----------------

    async def packet_parse(self, data: bytes) -> Packet:
        """Parse a single decrypted EcoFlow packet.

        The Connection class already handles ECDH/session key negotiation and
        decrypts the EncPacket wrapper. Device implementations must *only*
        deserialize the resulting EcoFlow Packet frame.
        """
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet) -> bool:
        """Parse raw heartbeat packets.

        Keep this resilient: if any heartbeat payload shape doesn't match the
        expected model, log and continue instead of crashing the integration.
        """

        self.reset_updated()
        processed = False

        def _set_metric(attr_name: str, ha_key: str, value: int | None) -> None:
            """Set an ad-hoc metric and notify HA only if it changed."""
            if value is None:
                return
            if value != getattr(self, attr_name, None):
                setattr(self, attr_name, value)
                self.update_state(ha_key, value)

        try:
            match (packet.src, packet.cmdSet, packet.cmdId):
                case (0x02, 0x20, 0x02):
                    # PD heartbeat
                    # Keep the mapped dataclass/protobuf decode for config fields.
                    self.update_from_bytes(Mr330PdHeart, packet.payload)

                    # Power rails: decode from fixed offsets in the PD payload.
                    # Offsets are 0-based within packet.payload (payload_len=0x79).
                    payload = packet.payload

                    # SOC is at payload[14] in your plaintext captures.
                    if len(payload) > 14:
                        soc = payload[14]
                        if soc != getattr(self, "battery_level", None):
                            self.battery_level = soc

                    ac_out = _normalize_watts(_u16le(payload, 15))
                    # When AC ports are disabled, EcoFlow may still report a
                    # small non-zero value here. Gate AC output by the AC-ports
                    # enable flag to avoid phantom AC load in Home Assistant.
                    if getattr(self, "ac_ports", None) is False:
                        ac_out = 0

                    ac_in = _normalize_watts(_u16le(payload, 17))
                    usbc = _normalize_watts(_u16le(payload, 50))
                    dc_out = _normalize_watts(_u16le(payload, 75))
                    # USB-A output in PD heartbeat is a single-byte watts value.
                    # Using u16 would combine the following flag byte and create
                    # bogus spikes like 261W (0x0105).
                    usba_raw = payload[112] if len(payload) > 112 else None
                    usba = _normalize_watts(usba_raw)

                    _set_metric("ac_output_power", "ac_output_power", ac_out)
                    _set_metric("ac_input_power", "ac_input_power", ac_in)
                    _set_metric("usbc_output_power", "usbc_output_power", usbc)
                    _set_metric("usba_output_power", "usba_output_power", usba)
                    _set_metric("dc_output_power", "dc_output_power", dc_out)

                    # Total input/output power for R2P is derived from the same
                    # rail values (AC/DC/USB). This keeps the totals independent
                    # of any protobuf mapping quirks and prevents stale/absurd
                    # values from sticking in HA.
                    out_sum = _sum_ints(ac_out, dc_out, usba, usbc)
                    if out_sum is not None:
                        _set_metric("output_power", "output_power", int(out_sum))

                    in_sum = _sum_ints(ac_in, getattr(self, "dc_input_power", None))
                    if in_sum is not None:
                        _set_metric("input_power", "input_power", int(in_sum))

                    processed = True

                case (0x03, 0x20, 0x02):
                    # EMS heartbeat
                    self.update_from_bytes(DirectEmsDeltaHeartbeatPack, packet.payload)
                    processed = True

                case (0x03, 0x20, 0x32):
                    # BMS heartbeat
                    self.update_from_bytes(DirectBmsMDeltaHeartbeatPack, packet.payload)
                    processed = True

                case (0x05, 0x20, 0x02):
                    # MPPT heartbeat
                    mppt = self.update_from_bytes(Mr330MpptHeart, packet.payload)

                    # XT60 input (solar or car).
                    dc_in = _normalize_watts(getattr(mppt, "in_watts", None))
                    if dc_in is None:
                        dc_in = 0
                    _set_metric("dc_input_power", "dc_input_power", dc_in)

                    # 12V/Car DC outputs (sum of known DC rails).
                    dc_out = _sum_ints(
                        _normalize_watts(getattr(mppt, "car_out_watts", None)),
                        _normalize_watts(getattr(mppt, "dcdc_12v_watts", None)),
                    )
                    if dc_out is None:
                        dc_out = 0
                    _set_metric("dc_output_power", "dc_output_power", int(dc_out))

                    # Solar vs car input split uses the device's own configured
                    # charge type (cfgChgType): 0=Auto, 1=Solar, 2=Car.
                    cfg_type = getattr(mppt, "cfg_chg_type", None)
                    solar_in = dc_in if cfg_type == 1 else 0
                    car_in = dc_in if cfg_type == 2 else 0
                    _set_metric("solar_input_power", "solar_input_power", int(solar_in))
                    _set_metric("car_input_power", "car_input_power", int(car_in))

                    # Keep input_power independent and up-to-date.
                    in_sum = _sum_ints(getattr(self, "ac_input_power", None), dc_in)
                    if in_sum is not None:
                        _set_metric("input_power", "input_power", int(in_sum))
                    processed = True

                case _:
                    return False

        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Failed parsing River2Pro packet src=0x%02x set=0x%02x id=0x%02x (len=%s)",
                packet.src,
                packet.cmdSet,
                packet.cmdId,
                len(packet.payload) if packet.payload else 0,
                exc_info=True,
            )
            return False

        for field_name in self.updated_fields:
            self.update_state(field_name, getattr(self, field_name, None))

        return processed

    # -----------------
    # Writes (Switches)
    # -----------------

    async def enable_ac_ports(self, enabled: bool):
        """AC Output ON/OFF."""
        payload = bytes([0x01 if enabled else 0x00] + [0xFF] * 6)
        packet = Packet(0x21, 0x05, 0x20, 0x42, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state("ac_ports", enabled)

    async def enable_dc_12v_port(self, enabled: bool):
        """DC Output (car/12V) ON/OFF."""
        payload = bytes([0x01 if enabled else 0x00])
        packet = Packet(0x21, 0x05, 0x20, 0x51, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state("dc_12v_port", enabled)

    async def enable_ac_xboost(self, enabled: bool):
        """X-Boost ON/OFF."""
        payload = bytes([0xFF, 0x01 if enabled else 0x00] + [0xFF] * 5)
        packet = Packet(0x21, 0x05, 0x20, 0x42, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state("ac_xboost", enabled)

    async def enable_ac_always_on(self, enabled: bool):
        """AC Always On ON/OFF."""
        payload = bytes([0x01 if enabled else 0x00, 0x05])
        packet = Packet(0x21, 0x02, 0x20, 0x5F, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state("ac_always_on", enabled)

    async def enable_energy_backup(self, enabled: bool):
        """Backup Reserve (UPS) ON/OFF.

        Your capture indicates payload format: [enabled u8][reserve u8][0x00][0x00].
        We keep a remembered reserve level, defaulting to 30%.
        """
        reserve = (
            self.energy_backup_battery_level
            if self.energy_backup_battery_level is not None
            else 30
        )
        reserve = max(0, min(int(reserve), 100))

        payload = bytes([0x01 if enabled else 0x00, reserve, 0x00, 0x00])
        packet = Packet(0x21, 0x02, 0x20, 0x5E, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state("energy_backup", enabled)


    # -----------------
    # Writes (Numbers)
    # -----------------

    async def set_energy_backup_battery_level(self, value: int) -> bool:
        """Set backup reserve percentage.

        Matches your captured 0x5E payload format: [1][percent][0x00][0x00].
        The River 3 implementation also enables energy backup when setting the
        reserve, so we do the same.
        """
        percent = max(0, min(int(value), 100))
        payload = bytes([0x01, percent, 0x00, 0x00])
        packet = Packet(0x21, 0x02, 0x20, 0x5E, payload, version=2)
        await self._conn.sendPacket(packet)

        self.update_state('energy_backup', True)
        self.update_state('energy_backup_battery_level', percent)
        return True

    async def set_battery_charge_limit_min(self, limit: int) -> bool:
        """Set discharge limit (minimum SoC)."""
        # App UI bounds for River 2 Pro: 0..30
        limit = max(0, min(int(limit), 30))
        if self.battery_charge_limit_max is not None and limit > int(self.battery_charge_limit_max):
            return False

        payload = bytes([limit])
        packet = Packet(0x21, 0x03, 0x20, 0x33, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state('battery_charge_limit_min', limit)
        return True

    async def set_battery_charge_limit_max(self, limit: int) -> bool:
        """Set charge limit (maximum SoC)."""
        # App UI bounds for River 2 Pro: 50..100
        limit = max(50, min(int(limit), 100))
        if self.battery_charge_limit_min is not None and limit < int(self.battery_charge_limit_min):
            return False

        payload = bytes([limit])
        packet = Packet(0x21, 0x03, 0x20, 0x31, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state('battery_charge_limit_max', limit)
        return True

    async def set_car_input_current_limit_ma(self, value_ma: int) -> bool:
        """Set car input current limit (mA).

        Captured cmd: dst=0x05, cmdSet=0x20, cmdId=0x47, payload=<u32 mA LE>.
        App options: 4000 / 6000 / 8000 mA.
        """
        value_ma = int(value_ma)
        if value_ma not in (4000, 6000, 8000):
            # Coerce to closest supported value
            value_ma = min((4000, 6000, 8000), key=lambda x: abs(x - value_ma))

        payload = struct.pack('<I', value_ma)
        packet = Packet(0x21, 0x05, 0x20, 0x47, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state('car_input_current_limit_ma', value_ma)
        return True

    async def set_dc_mode(self, value: int) -> bool:
        """Set DC input mode.

        Captured cmd: dst=0x05, cmdSet=0x20, cmdId=0x52, payload=<u8>.
        Values: 0=Auto, 1=Solar Recharging, 2=Car Recharging.
        """
        value = int(value)
        if value not in (0, 1, 2):
            value = 0

        payload = bytes([value])
        packet = Packet(0x21, 0x05, 0x20, 0x52, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state('dc_mode', value)
        return True

    async def set_ac_charge_speed_watts(self, watts: int) -> bool:
        """Set AC charge speed (W).

        Captured cmd: dst=0x05, cmdSet=0x20, cmdId=0x45, payload=<u16 W LE><0xFF>.
        App UI: 100..900 step 50, plus a special max of 940W.
        """
        watts = int(watts)

        allowed = {100 + 50 * i for i in range(0, 17)}  # 100..900
        allowed.add(940)
        if watts not in allowed:
            # Coerce into the nearest supported value
            watts = min(allowed, key=lambda x: abs(x - watts))

        payload = struct.pack('<H', watts) + b'\xFF'
        packet = Packet(0x21, 0x05, 0x20, 0x45, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state('ac_charge_speed_watts', watts)
        return True

    async def set_device_timeout_minutes(self, minutes: int) -> bool:
        """Set device timeout (standby) in minutes.

        Captured cmd: dst=0x05, cmdSet=0x20, cmdId=0x21, payload=<u16 minutes LE>.
        Use 0 for "Never".
        """
        minutes = max(0, min(int(minutes), 0xFFFF))
        payload = struct.pack('<H', minutes)
        packet = Packet(0x21, 0x05, 0x20, 0x21, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state('device_timeout_minutes', minutes)
        return True

    async def set_lcd_timeout_seconds(self, seconds: int) -> bool:
        """Set LCD timeout in seconds.

        Captured cmd: dst=0x05, cmdSet=0x20, cmdId=0x27, payload=<u16 seconds LE><0xFF>.
        Use 0 for "Never".
        """
        seconds = max(0, min(int(seconds), 0xFFFF))
        payload = struct.pack('<H', seconds) + b'\xFF'
        packet = Packet(0x21, 0x05, 0x20, 0x27, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state('lcd_timeout_seconds', seconds)
        return True

    async def set_ac_timeout_minutes(self, minutes: int) -> bool:
        """Set AC timeout in minutes.

        Captured cmd: dst=0x05, cmdSet=0x20, cmdId=0x99, payload=<u16 minutes LE>.
        Use 0 for "Never".
        """
        minutes = max(0, min(int(minutes), 0xFFFF))
        payload = struct.pack('<H', minutes)
        packet = Packet(0x21, 0x05, 0x20, 0x99, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state('ac_timeout_minutes', minutes)
        return True

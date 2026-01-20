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

        try:
            match (packet.src, packet.cmdSet, packet.cmdId):
                case (0x02, 0x20, 0x02):
                    # PD heartbeat
                    self.update_from_bytes(Mr330PdHeart, packet.payload)
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
                    self.update_from_bytes(Mr330MpptHeart, packet.payload)
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

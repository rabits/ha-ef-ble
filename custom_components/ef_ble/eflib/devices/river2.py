import logging

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..devicebase import DeviceBase
from ..model import (
    DirectBmsMDeltaHeartbeatPack,
    DirectEmsDeltaHeartbeatPack,
    Mr330MpptHeart,
    Mr330PdHeart,
)
from ..packet import Packet
from ..props import Field
from ..props.enums import IntFieldValue
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

_LOGGER = logging.getLogger(__name__)

# Raw-data mappers used by raw_field(...)
pb_pd = dataclass_attr_mapper(Mr330PdHeart)
pb_mppt = dataclass_attr_mapper(Mr330MpptHeart)
pb_ems = dataclass_attr_mapper(DirectEmsDeltaHeartbeatPack)
pb_bms = dataclass_attr_mapper(DirectBmsMDeltaHeartbeatPack)


class DCMode(IntFieldValue):
    AUTO = 0
    SOLAR = 1
    CAR = 2


def _sum_ints(*vals: int | None) -> int | None:
    total = 0
    seen = False
    for v in vals:
        if v is None:
            continue
        try:
            total += int(v)
            seen = True
        except Exception:  # noqa: BLE001
            continue
    return total if seen else None


def _u16le(buf: bytes, offset: int) -> int | None:
    """Read little-endian u16 from buf at offset, or None if out of range."""
    if offset < 0 or offset + 1 >= len(buf):
        return None
    return buf[offset] | (buf[offset + 1] << 8)


class Device(DeviceBase, RawDataProps):
    """EcoFlow River"""

    NAME_PREFIX = "EF-R2"
    SN_PREFIX = ()  # TODO(gnox): add regular r2 support after we get samples

    ac_ports = raw_field(pb_pd.cfg_ac_enabled, lambda x: x == 1)
    dc_12v_port = raw_field(pb_mppt.car_state, lambda x: x == 1)
    ac_xboost = raw_field(pb_mppt.cfg_ac_xboost, lambda x: x == 1)

    energy_backup = raw_field(pb_ems.open_ups_flag, lambda x: x == 1)
    energy_backup_battery_level = raw_field(pb_ems.open_oil_eb_soc)

    battery_charge_limit_min = raw_field(pb_ems.min_dsg_soc)
    battery_charge_limit_max = raw_field(pb_ems.max_charge_soc)

    battery_level = raw_field(pb_pd.soc)
    cell_temperature = raw_field(pb_bms.temp)

    input_power = raw_field(pb_pd.watts_in_sum)
    output_power = raw_field(pb_pd.watts_out_sum)

    dc_mode = raw_field(pb_mppt.cfg_chg_type, DCMode.from_value)

    ac_input_power = raw_field(pb_pd.ac_chg_power)
    ac_output_power = raw_field(pb_pd.ac_dsg_power)

    dc_port_input_power = raw_field(pb_mppt.in_watts)
    solar_input_power = Field[int]()
    car_input_power = Field[int]()
    # dc_output_power = raw_field(pb_pd.dc_dsg_power)
    dc_output_power = raw_field(pb_pd.dc_dsg_power)
    usbc_output_power = raw_field(pb_pd.typec1_watts)
    usba_output_power = raw_field(pb_pd.usb1_watt)

    dc_charging_max_amps = raw_field(pb_mppt.cfg_dc_chg_current, lambda x: x / 1000)
    ac_charge_speed_watts = raw_field(pb_mppt.cfg_chg_watts)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self.dc_charging_current_max = 8

    @classmethod
    def check(cls, sn: bytes):
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self):
        match self._sn[:4]:
            case "R601" | "R603":
                return "River 2"
            case "R621" | "R623":
                return "River 2 Pro"
            case "R611" | "R613":
                return "River 2 Max"
        return "River 2"

    @property
    def packet_version(self):
        return 2

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet) -> bool:
        self.reset_updated()
        processed = False

        match (packet.src, packet.cmdSet, packet.cmdId):
            case (0x02, 0x20, 0x02):
                self.update_from_bytes(Mr330PdHeart, packet.payload)

                # Power rails: decode from fixed offsets in the PD payload.
                # Offsets are 0-based within packet.payload (payload_len=0x79).
                # payload = packet.payload

                # ac_out = _normalize_watts(_u16le(payload, 15))
                # # When AC ports are disabled, EcoFlow may still report a
                # # small non-zero value here. Gate AC output by the AC-ports
                # # enable flag to avoid phantom AC load in Home Assistant.
                # if getattr(self, "ac_ports", None) is False:
                #     ac_out = 0

                # ac_in = _normalize_watts(_u16le(payload, 17))
                # usbc = _normalize_watts(_u16le(payload, 50))
                # dc_out = _normalize_watts(_u16le(payload, 75))
                # # USB-A output in PD heartbeat is a single-byte watts value.
                # # Using u16 would combine the following flag byte and create
                # # bogus spikes like 261W (0x0105).
                # usba_raw = payload[112] if len(payload) > 112 else None
                # usba = _normalize_watts(usba_raw)

                # _set_metric("ac_output_power", "ac_output_power", ac_out)
                # _set_metric("ac_input_power", "ac_input_power", ac_in)
                # _set_metric("usbc_output_power", "usbc_output_power", usbc)
                # _set_metric("usba_output_power", "usba_output_power", usba)
                # _set_metric("dc_output_power", "dc_output_power", dc_out)

                # Total input/output power for R2P is derived from the same
                # rail values (AC/DC/USB). This keeps the totals independent
                # of any protobuf mapping quirks and prevents stale/absurd
                # values from sticking in HA.
                # out_sum = _sum_ints(ac_out, dc_out, usba, usbc)
                # if out_sum is not None:
                #     _set_metric("output_power", "output_power", int(out_sum))

                # in_sum = _sum_ints(ac_in, getattr(self, "dc_input_power", None))
                # if in_sum is not None:
                #     _set_metric("input_power", "input_power", int(in_sum))

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
                self.car_input_power = (
                    self.dc_port_input_power if self.dc_mode == DCMode.CAR else 0
                )
                self.solar_input_power = (
                    self.dc_port_input_power if self.dc_mode == DCMode.SOLAR else 0
                )

                # # 12V/Car DC outputs (sum of known DC rails).
                # dc_out = _sum_ints(
                #     _normalize_watts(getattr(mppt, "car_out_watts", None)),
                #     _normalize_watts(getattr(mppt, "dcdc_12v_watts", None)),
                # )
                # if dc_out is None:
                #     dc_out = 0
                # _set_metric("dc_output_power", "dc_output_power", int(dc_out))

                # # Solar vs car input split uses the device's own configured
                # # charge type (cfgChgType): 0=Auto, 1=Solar, 2=Car.
                # cfg_type = getattr(mppt, "cfg_chg_type", None)
                # solar_in = dc_in if cfg_type == 1 else 0
                # car_in = dc_in if cfg_type == 2 else 0
                # _set_metric("solar_input_power", "solar_input_power", int(solar_in))
                # _set_metric("car_input_power", "car_input_power", int(car_in))

                # # Keep input_power independent and up-to-date.
                # in_sum = _sum_ints(getattr(self, "ac_input_power", None), dc_in)
                # if in_sum is not None:
                #     _set_metric("input_power", "input_power", int(in_sum))
                processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name, None))

        return processed

    async def enable_ac_ports(self, enabled: bool):
        """AC Output ON/OFF."""
        payload = bytes([1 if enabled else 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        packet = Packet(0x21, 0x05, 0x20, 0x42, payload, version=2)
        await self._conn.sendPacket(packet)

    async def enable_dc_12v_port(self, enabled: bool):
        """DC Output (car/12V) ON/OFF."""
        payload = bytes([0x01 if enabled else 0x00])
        packet = Packet(0x21, 0x05, 0x20, 0x51, payload, version=2)
        await self._conn.sendPacket(packet)

    async def enable_ac_xboost(self, enabled: bool):
        """X-Boost ON/OFF."""
        payload = bytes([0xFF, 0x01 if enabled else 0x00] + [0xFF] * 5)
        packet = Packet(0x21, 0x05, 0x20, 0x42, payload, version=2)
        await self._conn.sendPacket(packet)

    async def enable_ac_always_on(self, enabled: bool):
        """AC Always On ON/OFF."""
        payload = bytes([0x01 if enabled else 0x00, 0x05])
        packet = Packet(0x21, 0x02, 0x20, 0x5F, payload, version=2)
        await self._conn.sendPacket(packet)

    async def enable_energy_backup(self, enabled: bool):
        reserve = (
            self.energy_backup_battery_level
            if self.energy_backup_battery_level is not None
            else 30
        )
        reserve = max(0, min(int(reserve), 100))

        payload = bytes([0x01 if enabled else 0x00, reserve, 0x00, 0x00])
        packet = Packet(0x21, 0x02, 0x20, 0x5E, payload, version=2)
        await self._conn.sendPacket(packet)

    async def set_energy_backup_battery_level(self, value: int) -> bool:
        percent = max(0, min(int(value), 100))
        payload = bytes([0x01, percent, 0x00, 0x00])
        packet = Packet(0x21, 0x02, 0x20, 0x5E, payload, version=2)
        await self._conn.sendPacket(packet)
        return True

    async def set_battery_charge_limit_min(self, limit: int) -> bool:
        limit = max(0, min(int(limit), 30))
        if (
            self.battery_charge_limit_max is not None
            and limit > self.battery_charge_limit_max
        ):
            return False

        payload = bytes([limit])
        packet = Packet(0x21, 0x03, 0x20, 0x33, payload, version=2)
        await self._conn.sendPacket(packet)
        return True

    async def set_battery_charge_limit_max(self, limit: int) -> bool:
        if self.battery_charge_limit_min is not None and limit < int(
            self.battery_charge_limit_min
        ):
            return False

        payload = bytes([limit])
        packet = Packet(0x21, 0x03, 0x20, 0x31, payload, version=2)
        await self._conn.sendPacket(packet)
        return True

    async def set_dc_charging_amps_max(self, value: int) -> bool:
        packet = Packet(0x21, 0x05, 0x20, 0x47, value.to_bytes(), version=2)
        await self._conn.sendPacket(packet)
        return True

    async def set_dc_mode(self, value: DCMode) -> bool:
        payload = bytes([value])
        packet = Packet(0x21, 0x05, 0x20, 0x52, payload, version=2)
        await self._conn.sendPacket(packet)
        self.update_state("dc_mode", value)
        return True

    async def set_ac_charge_speed_watts(self, watts: int) -> bool:
        payload = watts.to_bytes(2, "little") + b"\xff"
        packet = Packet(0x21, 0x05, 0x20, 0x45, payload, version=2)
        await self._conn.sendPacket(packet)
        return True

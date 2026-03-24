"""EcoFlow PowerPulse EV charger (BLE / AC517 APL)."""

import logging
import struct
from typing import Iterator

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..packet import Packet
from ..props import Field, ProtobufProps
from ..props.enums import IntFieldValue
from ..props.utils import pround

_LOGGER = logging.getLogger(__name__)


def _iter_protobuf_fields(data: bytes) -> Iterator[tuple[int, int, object]]:
    """Yield (field_number, wire_type, decoded_value) for protobuf wire data."""

    idx = 0
    data_len = len(data)

    def _read_varint(start: int) -> tuple[int, int]:
        value = 0
        shift = 0
        pos = start
        while pos < data_len:
            byte = data[pos]
            pos += 1
            value |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                return value, pos
            shift += 7
            if shift > 63:
                break
        raise ValueError("invalid varint")

    while idx < data_len:
        key, idx = _read_varint(idx)
        field_number = key >> 3
        wire_type = key & 0x07

        if wire_type == 0:  # varint
            value, idx = _read_varint(idx)
            yield field_number, wire_type, value
        elif wire_type == 2:  # length-delimited
            size, idx = _read_varint(idx)
            end = idx + size
            if end > data_len:
                raise ValueError("truncated length-delimited field")
            yield field_number, wire_type, data[idx:end]
            idx = end
        elif wire_type == 5:  # fixed32
            end = idx + 4
            if end > data_len:
                raise ValueError("truncated fixed32 field")
            value = struct.unpack("<f", data[idx:end])[0]
            yield field_number, wire_type, value
            idx = end
        elif wire_type == 1:  # fixed64 (skip)
            idx += 8
            if idx > data_len:
                raise ValueError("truncated fixed64 field")
        else:
            raise ValueError(f"unsupported wire type: {wire_type}")


def _extract_cmd_2_2_33_metrics(payload: bytes) -> tuple[float | None, float | None, float | None]:
    """
    Extract power/voltage/current from 0x02/0x02/0x21 packet nested submessage.

    On C101 firmware we consistently observe:
      - top-level field 8 => nested submessage
      - nested field 4 (float) => charging power (W)
      - nested field 7 (float) => AC input voltage (V)
      - nested field 10 (float) => AC input current (A)
    """
    nested_payload: bytes | None = None
    for field_number, wire_type, value in _iter_protobuf_fields(payload):
        if field_number == 8 and wire_type == 2:
            nested_payload = value
            break

    if not nested_payload:
        return None, None, None

    power_w = voltage_v = current_a = None
    for field_number, wire_type, value in _iter_protobuf_fields(nested_payload):
        if wire_type != 5:
            continue
        if field_number == 4:
            power_w = float(value)
        elif field_number == 7:
            voltage_v = float(value)
        elif field_number == 10:
            current_a = float(value)

    return power_w, voltage_v, current_a


def _extract_cmd_2_2_33_state(payload: bytes) -> int | None:
    """Extract top-level state from 0x02/0x02/0x21 payload (field #1, varint)."""
    for field_number, wire_type, value in _iter_protobuf_fields(payload):
        if field_number == 1 and wire_type == 0:
            return int(value)
    return None


class AcPlugState(IntFieldValue):
    UNKNOWN = -1
    UNPLUGGED = 0
    PLUGGED_IN = 1
    CHARGING = 2
    CHARGE_COMPLETE = 3


class Device(DeviceBase, ProtobufProps):
    """PowerPulse"""

    # Only C101 (9.6 kW US EV charger) — verified; other PowerPulse SKUs stay unsupported.
    SN_PREFIX = (b"C101",)
    NAME_PREFIX = "EF-PP"

    output_power = Field[float]()
    ac_output_voltage = Field[float]()
    ac_output_current = Field[float]()
    ac_plug_state = Field[AcPlugState]()

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self) -> str:
        return "EcoFlow PowerPulse EV Charger (9.6 kW)"

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        self.reset_updated()
        # _LOGGER.debug(f"PowerPulse: data_parse packet: {packet.src} {packet.cmdSet} {packet.cmdId} {packet.payload}")

        # C101 telemetry path observed in logs:
        # status+metrics heartbeat over 0x02/0x02/0x21.
        if packet.src == 0x02 and packet.cmdSet == 0x02 and packet.cmdId == 0x21:
            try:
                power_w, voltage_v, current_a = _extract_cmd_2_2_33_metrics(packet.payload)
                state = _extract_cmd_2_2_33_state(packet.payload)
            except ValueError:
                power_w = voltage_v = current_a = None
                state = None

            if state == 1:
                self.ac_plug_state = AcPlugState.UNPLUGGED
            elif state == 2:
                self.ac_plug_state = AcPlugState.PLUGGED_IN
            elif state == 3:
                self.ac_plug_state = AcPlugState.CHARGING
            elif state == 6:
                self.ac_plug_state = AcPlugState.CHARGE_COMPLETE
            elif state is None and len(packet.payload) == 0:
                # Empty heartbeat carries no explicit plug state.
                self.ac_plug_state = AcPlugState.UNKNOWN

            # Small near-zero noise values can appear while unplugged/idle.
            if current_a is not None and abs(current_a) < 0.05:
                current_a = 0.0
            if power_w is not None and abs(power_w) < 1.0:
                power_w = 0.0

            if voltage_v is not None:
                self.ac_output_voltage = pround(1)(voltage_v)
            if current_a is not None:
                self.ac_output_current = pround(2)(current_a)
            if power_w is not None:
                self.output_power = pround(1)(power_w)

            if self.ac_output_voltage is None:
                self.ac_output_voltage = 0.0
            if self.ac_output_current is None:
                self.ac_output_current = 0.0
            if self.output_power is None:
                self.output_power = 0.0
            processed = True

        if (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

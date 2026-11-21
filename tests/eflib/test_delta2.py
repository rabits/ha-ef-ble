"""
Fault and diagnostic values of the Delta 2

The reference heartbeats are the real EMS, main BMS and inverter frames captured in
``test_delta2_plus.py``. The Delta 3 1500 is a Delta 2 subclass and sends the same
heartbeat models, so each test rewrites only the fields it varies and feeds the
frame to a Delta 2.
"""

import struct
from dataclasses import fields
from typing import get_type_hints

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.delta2 import Device
from custom_components.ef_ble.eflib.model import (
    DirectBmsMDeltaHeartbeatPack,
    DirectEmsDeltaHeartbeatPack,
    DirectInvDeltaHeartbeatPack,
)
from custom_components.ef_ble.eflib.model.base import RawData
from custom_components.ef_ble.eflib.packet import Packet

_EMS_FRAME = "aa023700272cb8e13d00024e03212002b9b9b9656fb8b81ef9b8b8b8dcbadbb8b88bafb8b88bafb8b8b9ba937efabbbbb8b9b99c74b8b84c6bb8b8b8b8dcbfb8b9b8b8b8b8bbb912d4"
_BMS_FRAME = "aa02be002c2fa04a5000024e03212032a0a1a2a0a0a0a085a0a0a2c28670a0a0315f5f5f80a190d5a0a0ccd3a0a090d5a0a0a1a0a0a0c4a6ada3adbfbe8282a0a090d5a0a0c86c64e2a0a0a0a0a0a0a0a0a0a0a0a0a3a0a0a3a0b0a5ada4ada3ada5ada5ada4ada4ada4ada4ada3ada5ada5ada5ada3ada6ada5ada4bfa0bea0bea0bea0f6908e918e91a3a15f5f90909090909090909090909090909090eea2a0a064e2a0a0a0a0167964e2a4a0a0a2a2a0a0a0a0a0a0a0a0a00c1da0a045f7a0a0a0a0a0a0a0a0a0a0a057e7e76885"
_INV_FRAME = "aa024600902c00000000010104212002000000001900010301b5013e0100676d030017070000323b710300ed010000322c0000000000000000000000000101708203000100000000000000d0020000000000000000005a08"

_EMS = (_EMS_FRAME, DirectEmsDeltaHeartbeatPack)
_BMS = (_BMS_FRAME, DirectBmsMDeltaHeartbeatPack)
_INV = (_INV_FRAME, DirectInvDeltaHeartbeatPack)


def _field_layout(model: type[RawData], name: str) -> tuple[int, str]:
    """Byte offset and struct format of field `name` (little-endian, in order)"""
    hints = get_type_hints(model, include_extras=True)
    layout = "<"
    for field in fields(model):
        field_fmt = hints[field.name].__metadata__[0]
        if field.name == name:
            return struct.calcsize(layout), field_fmt
        layout += field_fmt
    raise KeyError(name)


def _heartbeat(kind: tuple[str, type[RawData]], **values: int) -> Packet:
    """
    The reference heartbeat with `values` written into its payload

    The bytes are patched in place, because `RawData.pack` cannot rebuild the EMS
    heartbeat: its `3s` field breaks the one-character-per-field format slice.
    """
    frame, model = kind
    reference = Packet.from_bytes(bytes.fromhex(frame), xor_payload=True)
    payload = bytearray(reference.payload)
    for name, value in values.items():
        offset, field_fmt = _field_layout(model, name)
        packed = struct.pack("<" + field_fmt, value)
        payload[offset : offset + len(packed)] = packed
    return Packet(
        reference.src,
        0x21,
        reference.cmd_set,
        reference.cmd_id,
        bytes(payload),
        version=0x02,
    )


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "R331TEST1234")
    device._conn = mocker.AsyncMock()
    return device


@pytest.mark.parametrize(
    ("kind", "raw_attr", "raw_value", "field_name", "expected"),
    [
        (_INV, "err_code", 0x2B, Device.inverter_error_code, 0x2B),
        (_INV, "ac_in_freq", 60, Device.ac_input_frequency, 60),
        (_INV, "standby_mins", 30, Device.ac_standby_time, 30),
        (_BMS, "err_code", 0x10, Device.bms_error_code, 0x10),
        (_BMS, "bms_fault", 4, Device.bms_fault, 4),
        (_EMS, "bms_warning_state", 2, Device.bms_warning_state, 2),
    ],
    ids=[
        "inverter_error_code",
        "ac_input_frequency",
        "ac_standby_time",
        "bms_error_code",
        "bms_fault",
        "bms_warning_state",
    ],
)
async def test_delta2_maps_diagnostic_heartbeat_field(
    device, kind, raw_attr, raw_value, field_name, expected
):
    assert await device.data_parse(_heartbeat(kind, **{raw_attr: raw_value}))

    assert device.get_value(field_name) == expected


@pytest.mark.parametrize(
    ("inverter_error", "bms_error", "expected"),
    [
        (0x2B, 0, True),
        (0, 0x10, True),
        (0, 0, False),
    ],
    ids=["inverter_error", "bms_error", "no_error"],
)
async def test_delta2_error_occurred_follows_inverter_and_bms_error_codes(
    device, inverter_error, bms_error, expected
):
    assert await device.data_parse(_heartbeat(_INV, err_code=inverter_error))
    assert await device.data_parse(_heartbeat(_BMS, err_code=bms_error))

    assert device.error_occurred is expected

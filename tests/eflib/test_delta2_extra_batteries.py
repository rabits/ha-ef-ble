"""
Routing of per-pack BMS heartbeats for the Delta 2 family

Payloads are built from the real ``src=0x06`` heartbeat captured in
``test_delta2_plus.py``, rewriting only the fields each test varies. No recording
with two packs exists yet, so the ``num=2`` cases re-index the real pack-1 frame;
that both packs report on ``src=0x06`` and are told apart by the first payload byte
comes from a Delta 2 Max log with two attached. Identifying fields are replaced.
"""

import struct

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.delta2_max import Device
from custom_components.ef_ble.eflib.packet import Packet

# A real DirectBmsMDeltaHeartbeatPack: num=1, soc=100, maxCellTemp=32, vol=53262
_REAL_BMS_PAYLOAD = bytes.fromhex(
    "0101020000000041000002640ed00000020000002000204e00001f4e0000204e0000"
    "0100000064030d000d201e1e1e0003d0070000baffc74200000000000000009f0f0000"
)

# Byte offsets into that pack (little-endian, fields in declaration order)
_NUM = 0
_MAX_CELL_TEMP = 43
_INPUT_WATTS = 57
_OUTPUT_WATTS = 61


def _bms_payload(
    num: int,
    cell_temp: int = 32,
    input_watts: int = 0,
    output_watts: int = 0,
) -> bytes:
    payload = bytearray(_REAL_BMS_PAYLOAD)
    payload[_NUM] = num
    payload[_MAX_CELL_TEMP] = cell_temp
    payload[_INPUT_WATTS : _INPUT_WATTS + 4] = struct.pack("<I", input_watts)
    payload[_OUTPUT_WATTS : _OUTPUT_WATTS + 4] = struct.pack("<I", output_watts)
    return bytes(payload)


def _bms_packet(num: int, src: int = 0x06, **kwargs: int) -> Packet:
    """A BMS heartbeat as the device would send it"""
    return Packet(src, 0x21, 0x20, 0x32, _bms_payload(num, **kwargs), version=0x02)


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "R351TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def test_each_pack_lands_in_its_own_slot(device):
    """
    Two attached packs must not overwrite each other

    Regression test for battery 2 reading "unknown": routing keyed on the source
    address sent every extra battery into slot 1.
    """
    assert await device.data_parse(_bms_packet(num=1, cell_temp=25))
    assert await device.data_parse(_bms_packet(num=2, cell_temp=35))

    assert device.get_value(Device.battery_1_cell_temperature) == 25
    assert device.get_value(Device.battery_2_cell_temperature) == 35


async def test_second_pack_alone_does_not_populate_the_first_slot(device):
    assert await device.data_parse(_bms_packet(num=2, cell_temp=35))

    assert device.get_value(Device.battery_1_cell_temperature) is None
    assert device.get_value(Device.battery_2_cell_temperature) == 35


async def test_main_pack_routes_to_the_main_slot(device):
    assert await device.data_parse(_bms_packet(num=0, src=0x03))

    assert device.get_value(Device.battery_level_main) is not None
    assert device.get_value(Device.battery_1_cell_temperature) is None
    assert device.get_value(Device.battery_2_cell_temperature) is None


async def test_power_is_reported_per_pack(device):
    assert await device.data_parse(_bms_packet(num=1, input_watts=120, output_watts=0))
    assert await device.data_parse(_bms_packet(num=2, input_watts=0, output_watts=45))

    assert device.get_value(Device.battery_1_input_power) == 120
    assert device.get_value(Device.battery_1_output_power) == 0
    assert device.get_value(Device.battery_2_input_power) == 0
    assert device.get_value(Device.battery_2_output_power) == 45


async def test_routing_follows_the_pack_index_not_the_source_address(device):
    """Packs are told apart by `num`, so an unfamiliar address still routes correctly"""
    assert await device.data_parse(_bms_packet(num=2, src=0x07, cell_temp=35))

    assert device.get_value(Device.battery_2_cell_temperature) == 35


async def test_unknown_pack_index_is_left_unprocessed(device):
    """
    An unrecognized slot must fall through to the unhandled-packet log, not be
    silently written into some other pack's fields.
    """
    assert not await device.data_parse(_bms_packet(num=5))

    assert device.get_value(Device.battery_1_cell_temperature) is None
    assert device.get_value(Device.battery_2_cell_temperature) is None


_MODULE_INFO = bytes.fromhex(
    "015233363154455354313233343536373864b10e000001000000c900000000000000"
    "00000000000000000000000000000000000000000000000000000000000000c03f00"
    "008c420000a0400000a0410103"
)


async def test_module_info_report_is_recognized(device):
    """The per-module report is keyed by the same slot index as the BMS heartbeat"""
    packet = Packet(0x06, 0x21, 0x20, 0x58, _MODULE_INFO, version=0x02)

    assert await device.data_parse(packet) is True


async def test_module_info_with_unknown_slot_is_left_unprocessed(device):
    payload = bytearray(_MODULE_INFO)
    payload[0] = 5
    packet = Packet(0x06, 0x21, 0x20, 0x58, bytes(payload), version=0x02)

    assert await device.data_parse(packet) is False

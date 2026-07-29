import struct

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble import eflib
from custom_components.ef_ble.eflib.devices.power_hub import Device
from custom_components.ef_ble.eflib.packet import Packet


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    adv_data.manufacturer_data = {0xB5B5: b"\x12M109TEST0000001"}
    device = Device(ble_dev, adv_data, "M109TEST0000001")
    device._conn = mocker.AsyncMock()
    return device


async def test_power_hub_bms_total(device):
    payload = bytearray(35)
    payload[0] = 73
    struct.pack_into("<H", payload, 2, 120)
    struct.pack_into("<h", payload, 6, 8)
    struct.pack_into("<H", payload, 10, 3600)

    processed = await device.data_parse(Packet(0x03, 0x21, 0x03, 0x1C, bytes(payload)))

    assert processed is True
    assert device.battery_level == 73
    assert device.input_power == 120
    assert device.output_power == 8
    assert device.remaining_time_charging == 60
    assert device.remaining_time_discharging is None


async def test_power_hub_battery_record(device):
    payload = bytearray(128)
    payload[:16] = b"M101TEST00000001"
    payload[37] = 79
    struct.pack_into("<H", payload, 38, 53216)
    payload[46] = 30
    struct.pack_into("<H", payload, 65, 3332)
    struct.pack_into("<H", payload, 69, 3323)
    struct.pack_into("<I", payload, 78, 15)
    struct.pack_into("<i", payload, 82, 3)

    processed = await device.data_parse(
        Packet(0x03, 0x21, 0x03, 0x1A, bytes(payload), dsrc=2)
    )

    assert processed is True
    assert device.battery_2_enabled is True
    assert device.battery_2_sn == "M101TEST00000001"
    assert device.battery_2_battery_level == 79
    assert device.battery_2_voltage == 53.216
    assert device.battery_2_cell_temperature == 30
    assert device.battery_2_max_cell_voltage == 3.332
    assert device.battery_2_min_cell_voltage == 3.323
    assert device.battery_2_input_power == 15
    assert device.battery_2_output_power == 3


async def test_power_hub_mppt_record(device):
    payload = bytearray(136)
    struct.pack_into("<H", payload, 28, 53609)
    struct.pack_into("<H", payload, 32, 1690)
    struct.pack_into("<I", payload, 40, 34200)
    struct.pack_into("<H", payload, 44, 2651)
    struct.pack_into("<H", payload, 48, 90)
    struct.pack_into("<I", payload, 52, 27800)
    struct.pack_into("<H", payload, 56, 1400)
    struct.pack_into("<H", payload, 60, 38)
    payload[72] = 31
    payload[74] = 30

    processed = await device.data_parse(Packet(0x05, 0x21, 0x05, 0x20, bytes(payload)))

    assert processed is True
    assert device.battery_voltage == 53.609
    assert device.battery_current == 1.69
    assert device.pv_voltage_1 == 34.2
    assert device.pv_current_1 == 2.651
    assert device.pv_power_1 == 90
    assert device.pv_voltage_2 == 27.8
    assert device.pv_current_2 == 1.4
    assert device.pv_power_2 == 38
    assert device.pv_temperature_1 == 31
    assert device.pv_temperature_2 == 30


def test_new_device_selects_power_hub_before_unsupported(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    adv_data.manufacturer_data = {0xB5B5: b"\x12M109TEST0000001"}

    assert isinstance(eflib.NewDevice(ble_dev, adv_data), Device)


def test_power_hub_uses_fast_in_place_reconnect():
    assert Device.RECONNECT_IN_PLACE is True
    assert Device.RECONNECT_DELAY == 1.0

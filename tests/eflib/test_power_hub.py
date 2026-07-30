import struct

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble import eflib
from custom_components.ef_ble.eflib.devices.power_hub import Device
from custom_components.ef_ble.eflib.model import (
    PowerHubBatteryData,
    PowerHubBmsData,
    PowerHubMpptData,
)
from custom_components.ef_ble.eflib.packet import Packet

# Real night-time payloads with every serial-bearing byte replaced.
_MASKED_NIGHT_BATTERY = bytes.fromhex(
    "4d31303154455354303030303030303138c7000082020302ee0c00000300000002"
    "0000000047cacf0000c3ffffff1e0007a086010059850100611301003100000004"
    "0d0000f90c00001e1d1d1d0000000000030000001337000000640a0000000000"
    "000000003c00000014500003021d1d0300002cc9000000000002008e1300"
)
_MASKED_NIGHT_BMS_TOTAL = bytes.fromhex(
    "4900000000000700000077a2010000640a1450003c000000002a01ffff000000000000"
)
_MASKED_NIGHT_MPPT = bytes.fromhex(
    "000000000000000000000000000000000000000000000000af0004009acf0000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "8d000000000000001f001e000000010101000000000000000000000000000000"
    "5802000058020000000000010000000000000000820082000000000000000000"
    "0000000000000000"
)


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
    struct.pack_into("<i", payload, 2, 120)
    struct.pack_into("<i", payload, 6, 8)
    struct.pack_into("<H", payload, 10, 3600)

    processed = await device.data_parse(Packet(0x03, 0x21, 0x03, 0x1C, bytes(payload)))

    assert processed is True
    assert device.battery_level == 73
    assert device.input_power == 120
    assert device.output_power == 8


async def test_power_hub_battery_record(device):
    payload = bytearray(128)
    payload[:16] = b"M101TEST00000001"
    payload[37] = 79
    struct.pack_into("<i", payload, 38, 53216)
    struct.pack_into("<i", payload, 42, -61)
    struct.pack_into("<b", payload, 46, 30)
    struct.pack_into("<i", payload, 65, 3332)
    struct.pack_into("<i", payload, 69, 3323)
    struct.pack_into("<b", payload, 73, 31)
    struct.pack_into("<b", payload, 74, 29)
    struct.pack_into("<i", payload, 78, 15)
    struct.pack_into("<i", payload, 82, 3)

    processed = await device.data_parse(
        Packet(0x03, 0x21, 0x03, 0x1A, bytes(payload), dsrc=2)
    )

    assert processed is True
    assert device.battery_2_enabled is True
    assert device.battery_2_sn == "M101TEST00000001"
    assert device.battery_2_battery_level == 79
    assert device.battery_2_voltage == 53.216
    assert device.battery_2_battery_temperature == 30
    assert device.battery_2_max_cell_temperature == 31
    assert device.battery_2_min_cell_temperature == 29
    assert device.battery_2_max_cell_voltage == 3.332
    assert device.battery_2_min_cell_voltage == 3.323
    assert device.battery_2_input_power == 15
    assert device.battery_2_output_power == 3
    assert PowerHubBatteryData.from_bytes(payload).current == -61


async def test_power_hub_mppt_record(device):
    payload = bytearray(136)
    struct.pack_into("<i", payload, 28, 53609)
    struct.pack_into("<i", payload, 32, -1690)
    struct.pack_into("<i", payload, 36, -90)
    struct.pack_into("<i", payload, 40, 34200)
    struct.pack_into("<i", payload, 44, 2651)
    struct.pack_into("<i", payload, 48, 90)
    struct.pack_into("<i", payload, 52, 27800)
    struct.pack_into("<i", payload, 56, 1400)
    struct.pack_into("<i", payload, 60, 38)
    struct.pack_into("<h", payload, 72, -5)
    struct.pack_into("<h", payload, 74, 30)
    struct.pack_into("<h", payload, 76, 28)

    processed = await device.data_parse(Packet(0x05, 0x21, 0x05, 0x20, bytes(payload)))

    assert processed is True
    assert device.battery_voltage == 53.609
    assert device.battery_current == -1.69
    assert device.pv_voltage_1 == 34.2
    assert device.pv_current_1 == 2.651
    assert device.pv_power_1 == 90
    assert device.pv_voltage_2 == 27.8
    assert device.pv_current_2 == 1.4
    assert device.pv_power_2 == 38
    assert device.pv_heatsink_temperature_1 == -5
    assert device.pv_heatsink_temperature_2 == 30
    assert device.pcb_temperature == 28


def test_power_hub_masked_captured_night_payloads():
    battery = PowerHubBatteryData.from_bytes(_MASKED_NIGHT_BATTERY)
    total = PowerHubBmsData.from_bytes(_MASKED_NIGHT_BMS_TOTAL)
    mppt = PowerHubMpptData.from_bytes(_MASKED_NIGHT_MPPT)

    assert (battery.soc, battery.voltage, battery.current) == (71, 53194, -61)
    assert (battery.max_cell_voltage, battery.min_cell_voltage) == (3332, 3321)
    assert (battery.max_cell_temperature, battery.min_cell_temperature) == (30, 29)
    assert (battery.input_power, battery.output_power) == (0, 3)
    assert (total.soc, total.charge_discharge_state) == (73, 0)
    assert (total.input_power, total.output_power) == (0, 7)
    assert (mppt.battery_voltage, mppt.battery_current) == (53146, 0)
    assert (mppt.heatsink_temperature_1, mppt.heatsink_temperature_2) == (31, 30)


def test_power_hub_expires_unseen_battery_slots(device):
    device._seen_battery_slots = {1}
    device.battery_1_enabled = True
    device.battery_1_battery_level = 70
    device.battery_2_enabled = True
    device.battery_2_battery_level = 60
    device.battery_2_voltage = 52.5

    device._expire_missing_batteries()

    assert device.battery_1_enabled is True
    assert device.battery_1_battery_level == 70
    assert device.battery_2_enabled is False
    assert device.battery_2_battery_level is None
    assert device.battery_2_voltage is None


def test_new_device_selects_power_hub_before_unsupported(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    adv_data.manufacturer_data = {0xB5B5: b"\x12M109TEST0000001"}

    assert isinstance(eflib.NewDevice(ble_dev, adv_data), Device)


def test_power_hub_field_groups_do_not_shadow_main_sensors(device):
    assert not hasattr(device, "battery_input_power")
    assert not hasattr(device, "battery_output_power")
    assert not hasattr(device, "battery_temperature")


def test_power_hub_stays_available_during_transient_reconnect(device):
    device._conn.is_connected = False

    assert device.is_available is False

    device.set_reconnecting(True)
    assert device.is_available is True

    device.set_reconnecting(False)
    assert device.is_available is False

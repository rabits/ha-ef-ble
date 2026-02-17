import pytest
from google.protobuf import text_format
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices import _powerstream
from custom_components.ef_ble.eflib.packet import Packet
from custom_components.ef_ble.eflib.pb import wn511_sys_pb2
from custom_components.ef_ble.eflib.props import Field

_heartbeat_msg_str = """
pv1_input_volt: 2305
pv1_input_cur: 42
pv1_input_watts: 968
pv1_temp: 350

pv2_input_volt: 2280
pv2_input_cur: 38
pv2_input_watts: 866
pv2_temp: 340

bat_input_volt: 520
bat_input_cur: 15
bat_input_watts: 78
bat_temp: 270
bat_soc: 65

inv_input_volt: 3400
inv_op_volt: 2305
inv_output_cur: 43
inv_output_watts: 990
inv_temp: 380
inv_freq: 500
"""


@pytest.fixture
def heartbeat_message():
    return text_format.Merge(_heartbeat_msg_str, wn511_sys_pb2.inverter_heartbeat())


@pytest.fixture
def device(mocker: MockerFixture):
    mocker.patch("custom_components.ef_ble.eflib.devicebase.DeviceLogger")
    dev = _powerstream.Device(mocker.AsyncMock(), mocker.Mock(), "[sn]")
    dev._conn = mocker.AsyncMock()
    return dev


async def test_data_parse_updates_all_fields(device, heartbeat_message):
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x14,
        cmd_id=0x01,
        payload=heartbeat_message.SerializeToString(),
    )

    result = await device.data_parse(packet)
    assert result is True

    expected_updated_fields: list[Field] = [
        _powerstream.Device.pv_power_1,
        _powerstream.Device.pv_voltage_1,
        _powerstream.Device.pv_current_1,
        _powerstream.Device.pv_temperature_1,
        _powerstream.Device.pv_power_2,
        _powerstream.Device.pv_voltage_2,
        _powerstream.Device.pv_current_2,
        _powerstream.Device.pv_temperature_2,
        _powerstream.Device.battery_level,
        _powerstream.Device.battery_power,
        _powerstream.Device.battery_temperature,
        _powerstream.Device.grid_power,
        _powerstream.Device.grid_voltage,
        _powerstream.Device.grid_current,
        _powerstream.Device.grid_frequency,
        _powerstream.Device.inverter_temperature,
    ]

    for field in expected_updated_fields:
        assert field.public_name in device.updated_fields
        assert getattr(device, field.public_name) is not None


async def test_div10_transform_values(device, heartbeat_message):
    """Verify tenths-based values are correctly divided by 10."""
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x14,
        cmd_id=0x01,
        payload=heartbeat_message.SerializeToString(),
    )

    await device.data_parse(packet)

    # PV1: 2305 -> 230.5V, 42 -> 4.2A, 968 -> 96.8W, 350 -> 35.0C
    assert device.pv_voltage_1 == 230.5
    assert device.pv_current_1 == 4.2
    assert device.pv_power_1 == 96.8
    assert device.pv_temperature_1 == 35.0

    # PV2: 2280 -> 228.0V, 38 -> 3.8A, 866 -> 86.6W, 340 -> 34.0C
    assert device.pv_voltage_2 == 228.0
    assert device.pv_current_2 == 3.8
    assert device.pv_power_2 == 86.6
    assert device.pv_temperature_2 == 34.0

    # Battery: 78 -> 7.8W, 270 -> 27.0C, soc untransformed
    assert device.battery_power == 7.8
    assert device.battery_temperature == 27.0
    assert device.battery_level == 65

    # Inverter: 2305 -> 230.5V, 43 -> 4.3A, 990 -> 99.0W, 380 -> 38.0C, 500 -> 50.0Hz
    assert device.grid_voltage == 230.5
    assert device.grid_current == 4.3
    assert device.grid_power == 99.0
    assert device.inverter_temperature == 38.0
    assert device.grid_frequency == 50.0


async def test_unmatched_cmdset_returns_false(device, heartbeat_message):
    """Packets with non-matching cmdSet should not be processed."""
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0xFF,
        cmd_id=0x01,
        payload=heartbeat_message.SerializeToString(),
    )

    result = await device.data_parse(packet)
    assert result is False
    assert len(device.updated_fields) == 0

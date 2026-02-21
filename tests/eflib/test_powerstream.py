import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.powerstream import Device


@pytest.fixture
def packet_sequence():
    """
    Raw packet sequence captured from a PowerStream device

    Packet types cover all main modules:
    - src=0x35, cmdSet=0x14, cmdId=0x01: inverter_heartbeat (PV, battery, grid data)
    - src=0x35, cmdSet=0x14, cmdId=0x04: inv_heartbeat_type2 (system parameters)
    """
    return [
        "aa13fe01b90de03d00000000352101011401e8e0f0e0f8e0c0e0c8e0d0e0d8e0a0e0a8e0b0e0b8e480e488e590e398e660e14ae268e148f770e1e278e1dc40e156e248e130e250e145fa58e1e520e154e128e14ce230e16be438e149e400e1e008e1e010e132e118e1ff60e2e068e20fc170e256e278e2e040e26ff248e201e250e210e158e2e020e213e330e2e238e2f100e2e008e2e010e2e018e2e060e310e168e3e070e3e078e3e040e38448e3e150e3e058e3e020e36de128e3e230e320de38e345b600e300c608e3e010e310e118e3e060e4e068e4e070e410e178e410e140e4e748e4e050e4e058e4e020e4e028e4e030e4400bc138e43010d300e4e508e4e810e4e018e420de60e5e068e5e070e510e178e5391f1f1f1f1f1f1f1fe140e5e048e55ee150e53fd058e510ce70e600d078e620de40e6e148e6c350e66d1f15c258e6e120e64c53745ee628e624755e0de630e6203166601d1f1f1f1fe138e6e100e6e008e605e110e6e068e7e170e76c79372ce678e7aa40e7d448e7e050e7e058e78820e720de28e7e038e774ba00e7e608e7e315e7b9d699a918e73ce660e856f168e872f870e8e078e8e040e8e048e872f850e8c858e8e020e8391f1f1f1f1f1f1f1fe128e8e038e8e000e8e008e8fa10e8e018e8e360e9e068e9e070e9e078e9e040e9e048e9e050e9e020e970fc28e967433c2ce630e970fc38e9e000e9e008e9e010e9e018e9e060eae0ef43",
        "aa1352015d0dde3d00000000352101011404d6dfcedec6dffedef6deeedee6ba9ede96de8ede86dfbe2edfb6deaedea660d85edfda56df7e35ff4edf0e2eed46dfdd7edfde76dfdb6edf60df66dfd61edf01ee16dfde0edf2ef006df3eee3edf1ee036dfdf2edfdf26dffd5edc6a718056dcdd4edc9a46dcea7edcde76dcde6edcde66dcde1edcde16dcde0edcde06dcdf3edcde36dc3bdf2edcde26dcde5eddde56ddde4eddde7edd072121212121212121df76ddde6edddf66dddf1edddf16ddde0edddc06ddde3edddf36dddf2eddc226dddc54da52dfcedfc6dcf621585ec6eef0e61442dd9e062f21212121212121df96cb8edf865e2fdabe687edcb65e2fdaae6e5bdda6ba5edf2ec756df33c74edfc946dfcb7edfc676dfc866dfdd1edf5e2fda13df3349e69c06dfbe3edf40d736dfdf2edfdf26dfdf5edc7677dd56dc5646db46dcba7edcdd76dcc11edc7b8816dc3ef80edcdf03dc7aee269f36dcdc2edcdfbcc5",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "HW51TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def test_powerstream_parses_all_packets_successfully(device, packet_sequence):
    expected_packets = [
        (0x35, 0x14, 0x01),  # inverter_heartbeat
        (0x35, 0x14, 0x04),  # inv_heartbeat_type2
    ]

    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        expected_src, expected_cmdSet, expected_cmdId = expected_packets[i]

        assert packet is not None, f"Packet {i} failed to parse"
        assert packet.src == expected_src, (
            f"Packet {i} has unexpected src: {packet.src:#04x} != {expected_src:#04x}"
        )
        assert packet.cmdSet == expected_cmdSet, (
            f"Packet {i} has unexpected cmdSet: {packet.cmdSet:#04x} != {expected_cmdSet:#04x}"
        )
        assert packet.cmdId == expected_cmdId, (
            f"Packet {i} has unexpected cmdId: {packet.cmdId:#04x} != {expected_cmdId:#04x}"
        )


async def test_powerstream_processes_key_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        if i < 2:
            assert processed is True, f"Packet {i} was not processed"
        else:
            assert processed is False, f"Packet {i} should not be processed"


async def test_powerstream_updates_battery_level(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    assert Device.battery_level in device.updated_fields
    battery_level = getattr(device, Device.battery_level)
    assert battery_level is not None
    assert isinstance(battery_level, (int, float))
    assert 0 <= battery_level <= 100, f"Battery level {battery_level} out of range"


async def test_powerstream_updates_pv_power_fields(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    pv_field_names = [
        Device.pv_power_1,
        Device.pv_voltage_1,
        Device.pv_current_1,
        Device.pv_temperature_1,
        Device.pv_power_2,
        Device.pv_voltage_2,
        Device.pv_current_2,
        Device.pv_temperature_2,
    ]

    for field_name in pv_field_names:
        value = getattr(device, field_name)
        assert isinstance(value, (int, float)), (
            f"PV field {field_name} has wrong type: {type(value)}"
        )


async def test_powerstream_updates_grid_fields(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    grid_field_names = [
        Device.grid_power,
        Device.grid_voltage,
        Device.grid_current,
        Device.grid_frequency,
        Device.inverter_temperature,
    ]

    for field_name in grid_field_names:
        value = getattr(device, field_name)
        assert isinstance(value, (int, float)), (
            f"Grid field {field_name} has wrong type: {type(value)}"
        )


async def test_powerstream_field_types_are_consistent(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    numeric_fields = [
        Device.battery_level,
        Device.battery_power,
        Device.battery_temperature,
        Device.pv_power_1,
        Device.pv_voltage_1,
        Device.pv_current_1,
        Device.pv_temperature_1,
        Device.pv_power_2,
        Device.pv_voltage_2,
        Device.pv_current_2,
        Device.pv_temperature_2,
        Device.grid_power,
        Device.grid_voltage,
        Device.grid_current,
        Device.grid_frequency,
        Device.inverter_temperature,
    ]

    for field_name in numeric_fields:
        value = getattr(device, field_name, None)
        if value is not None:
            assert isinstance(value, (int, float)), (
                f"Field {field_name} has wrong type: {type(value)}"
            )


async def test_powerstream_battery_soc_values_are_valid(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    if Device.battery_level in device.updated_fields:
        battery_level = device.battery_level
        assert battery_level is not None
        assert 0 <= battery_level <= 100, (
            f"Battery level {battery_level} is out of valid range (0-100%)"
        )


async def test_powerstream_exact_values_from_known_packets(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    expected = {
        Device.battery_level: 31,
        Device.battery_power: 0.0,
        Device.battery_temperature: 21.0,
        Device.pv_power_1: 6.0,
        Device.pv_voltage_1: 29.8,
        Device.pv_current_1: 0.2,
        Device.pv_temperature_1: 31.0,
        Device.pv_power_2: 18.0,
        Device.pv_voltage_2: 33.6,
        Device.pv_current_2: 0.5,
        Device.pv_temperature_2: 30.0,
        Device.grid_power: 24.0,
        Device.grid_voltage: 231.9,
        Device.grid_current: 35.3,
        Device.grid_frequency: 49.9,
        Device.inverter_temperature: 0.0,
    }

    for field_name, expected_value in expected.items():
        actual_value = getattr(device, field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value}, got {actual_value}"
        )

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.delta3_max_plus import Device


@pytest.fixture
def packet_sequence():
    """Raw packet sequence captured from a Delta 3 Max Plus device"""
    return [
        "aa13ff00ab0d4cb80400000002210101fe15444c64cc4d744c0c7ec44d4cdc4de04ed44d4cec4d4c844d4ca64b6c464a444d5c4d5444464a444d5c4f545e464a444e5c4d5444464a444e5c4f545ee4444cfe444b09382f6319180ff4444dac444cdc454cd4454cfc474dd4404cd44170ec414ce4414c96414cd4424dd9434c4c8a0ed1434c4c840e8c438cf44ebc43b308b443b328dc5c59d45c5aec5c54e45c56f95c4c4c8a0ef15c4c4c840eac5cb308a45cb328bc5c28b45c4cd45d4d845d4c9c5d4cd45a4ca4544cbc544ce4574cfc574cf4574cdc504c9450f45bac50ec4abc50b153d4514dec514ce4519cfc9d804ab470caccc844ce715c464a44b3b3b3b343464a44b3b3b3b343c4714cec174c3ae9",
        "aa133c017e0d4db80400000002210101fe15504d4d4d4d684d4d4d4d004d4d4d4d184d4d4d4d104d4d4d4d284d4d4d4d25433d4d3543cd4c43c54f49e04f4d4d4d4da54f41bd4f4bb54f41e04e4d4d4d4df84e4d4d4d4df8494d4d4d4da0494d4d4d4dbd494db5494dc54845dd4871e84b4d4d4d4d8f45414749454c5d454749454e5d5f8745414749454c5d454749454e5d5fb5454dcd4459c544298d4443854443b8444d4d4d4dcd5c59c55c17dd5c4ca55c4dbd5c4d805f4d4d3d8c8d5b41805b4d4d4d4d9d5b4c955b4dad5b4ca55b45bd5b71b55b43c85a4d4d4d4d87554d9d554d95554dad554dbd5441e5574cfd574df5574d8d574d80574d4d4d4dbd574c8d514da5517f8f715947495d4c555447495d4f5554474b454c5d4e556c87714747454d4d4d4d4d4d4d4d957143af715b47594d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4dd57043b5024c7b75",
        "aa13c200bb0d4eb80400000002210101fe15be4f4ea64d4ebe4d7cd64b4eee4b4ee64b4efe4b4ef64b4e8c4b5e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e864b4e9e4bd3cece56944b5c445e4e4e4e4e4e4e4e4e4e4e4e4e4e4e4e4eae494ebc464e9e424ec643ee48de404ebe40f6599e544f965417ae544ab6544ccc5569446bceced6d84aceceeed84a4ef9f64c8ef64ce6f84c4e4e4e4e4e4eb4d7b629deec8ade4f4f4ec4555e0a7d0b7f1a0b1d1a7f7c7d7a7b787976de55d3cece56d6554eee554c9e52ae5c9b6b4e4e4e4ec6014ed62e4febd6",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "D3M1TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def test_delta3_max_plus_parses_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))

        assert packet is not None, f"Packet {i} failed to parse"
        assert packet.src == 0x02, f"Packet {i} has unexpected src: {packet.src:#04x}"
        assert packet.cmd_set == 0xFE, (
            f"Packet {i} has unexpected cmd_set: {packet.cmd_set:#04x}"
        )
        assert packet.cmd_id == 0x15, (
            f"Packet {i} has unexpected cmd_id: {packet.cmd_id:#04x}"
        )


async def test_delta3_max_plus_processes_all_packets_successfully(
    device, packet_sequence
):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_delta3_max_plus_updates_battery_level(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    assert Device.battery_level.public_name in device.updated_fields
    assert device.battery_level == 99.0


async def test_delta3_max_plus_exact_values_from_known_packets(device, packet_sequence):
    """Test that known packet data produces exact expected values"""
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.battery_level: 99.0,
        Device.battery_level_main: 99.0,
        Device.ac_charging_speed: 800,
        Device.cell_temperature: 22,
        Device.max_ac_charging_power: 2400,
        Device.battery_charge_limit_min: 0,
        Device.battery_charge_limit_max: 100,
        Device.remaining_time_charging: 12927,
        Device.remaining_time_discharging: 8831,
        Device.plugged_in_ac: False,
        Device.ac_ports: True,
        Device.ac_ports_2: True,
        Device.ac_power_1: 0.0,
        Device.ac_power_2: 0.0,
        Device.usbc3_output_power: 0.0,
        Device.energy_backup: False,
        Device.energy_backup_battery_level: 50,
        Device.input_power: 0.0,
        Device.output_power: 0.0,
    }

    for field, expected_value in expected.items():
        value = device.get_value(field)
        assert value == expected_value, (
            f"Field {field.public_name} is {value!r}, expected {expected_value!r}"
        )

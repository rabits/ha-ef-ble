import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.delta2_plus import Device


@pytest.fixture
def packet_sequence():
    """
    Raw packet sequence captured from a Delta 3 1500 (Delta 2 Plus) device

    Packet types cover all main modules:
    - src=0x02, cmdSet=0x20, cmdId=0x02: PdHeart (power delivery)
    - src=0x03, cmdSet=0x03, cmdId=0x0e: AllKitDetailData
    - src=0x03, cmdSet=0x20, cmdId=0x02: EmsDeltaHeartbeatPack (energy management)
    - src=0x03, cmdSet=0x20, cmdId=0x32: BmsHeartbeatBatteryMain (main battery)
    - src=0x04, cmdSet=0x20, cmdId=0x02: InvDeltaHeartbeatPack (inverter)
    - src=0x05, cmdSet=0x20, cmdId=0x02: MpptHeart (solar controller)
    - src=0x06, cmdSet=0x20, cmdId=0x32: BmsHeartbeatBattery1 (addon battery)
    """
    return [
        "aa028500422c000000000200022120024e000000004d0000010000000000623e01b501cde8ffff0000000000000000000000002978000000030000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b5013e0100000000010000005005000000000000000c55",
        "aa025300860db6e13d0000000321030eb7e5b6b4b6b7e6858087e2f3e5e2878485828380818ef9b6b1b6b7f7b6b6b4b4b6b6b4b6b6b6b60c4971f4d2b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b64269",
        "aa023700272cb8e13d00024e03212002b9b9b9656fb8b81ef9b8b8b8dcbadbb8b88bafb8b88bafb8b8b9ba937efabbbbb8b9b99c74b8b84c6bb8b8b8b8dcbfb8b9b8b8b8b8bbb912d4",
        "aa02be002c2fa04a5000024e03212032a0a1a2a0a0a0a085a0a0a2c28670a0a0315f5f5f80a190d5a0a0ccd3a0a090d5a0a0a1a0a0a0c4a6ada3adbfbe8282a0a090d5a0a0c86c64e2a0a0a0a0a0a0a0a0a0a0a0a0a3a0a0a3a0b0a5ada4ada3ada5ada5ada4ada4ada4ada4ada3ada5ada5ada5ada3ada6ada5ada4bfa0bea0bea0bea0f6908e918e91a3a15f5f90909090909090909090909090909090eea2a0a064e2a0a0a0a0167964e2a4a0a0a2a2a0a0a0a0a0a0a0a0a00c1da0a045f7a0a0a0a0a0a0a0a0a0a0a057e7e76885",
        "aa024600902c00000000010104212002000000001900010301b5013e0100676d030017070000323b710300ed010000322c0000000000000000000000000101708203000100000000000000d0020000000000000000005a08",
        "aa025e006f2c000000000101052120020000000026000106e0050000000000000000e3cd0000000000000000270000000000000000000000000000006100000000000000000027000000000000401f0000000101e600000032dc05d00200d002d002780000000000000000000000044f",
        "aa023301742ff5633300074f06212032f4f4f7f5f5f5f5b4f5f5f791fb25f5f5f7f5f5f5d5f5d5bbf5f5eabbf5f5d5bbf5f5f4f5f5f591f6f8f5f8d5ebebebf5f625f2f5f54f0a32b7f5f5f5f5f5f5f5f56afaf5f5f5f5f5f6f5e5f5f8f5f8f5f8f4f8f5f8f5f8f4f8f4f8f4f8f4f8f7f8f5f8f6f8f7f8f4f8f4f8f1ebf5ebf5d5f5ebf5a3c4dbc5dbc4f3f40a0aa5c6c3c4afc4bdb4a5bdc6c3c5c7c7cdbaf22cde3db7a5a0a0cab9d93db70a0a0a0af6f5f5f5f5f5f5f5f5f5fc9ff5f55dc4f5f5f5f53db7f5f5f5f5f5f53db7f7ebf5ebf5f4d5f5f5f4eaf5d5f5d5f5f5f5f5f5eaf5eaf5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f6f5f5f5d234f5f5e2d5f4f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f526f0f5f56df7f5f5a5c6c3c4a5c2c5cda5bdc6c3c5c4c1c2f5f8f2",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.Mock()
    device = Device(ble_dev, adv_data, "D361TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def test_delta2_plus_parses_all_packets_successfully(device, packet_sequence):
    expected_packets = [
        (0x02, 0x20, 0x02),  # PdHeart
        (0x03, 0x03, 0x0E),  # AllKitDetailData
        (0x03, 0x20, 0x02),  # EmsDeltaHeartbeatPack
        (0x03, 0x20, 0x32),  # BmsHeartbeatBatteryMain
        (0x04, 0x20, 0x02),  # InvDeltaHeartbeatPack
        (0x05, 0x20, 0x02),  # MpptHeart
        (0x06, 0x20, 0x32),  # BmsHeartbeatBattery1
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


async def test_delta2_plus_processes_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_delta2_plus_updates_battery_level(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    battery_fields = [
        Device.battery_level,
        Device.battery_level_main,
        Device.battery_1_battery_level,
    ]

    for field_name in battery_fields:
        value = getattr(device, field_name)
        if value is not None and isinstance(value, (int, float)):
            assert 0 <= value <= 100, f"{field_name} value {value} out of range"


async def test_delta2_plus_updates_power_fields(device, packet_sequence):
    # Process all packets to populate power fields
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    # Check that at least some fields were updated (packet parsing worked)
    assert len(device.updated_fields) > 0, (
        "No fields were updated after processing packets"
    )

    # If power fields exist and were updated, verify their types
    power_field_names = [
        Device.input_power,
        Device.output_power,
        Device.ac_output_power,
        Device.usbc_output_power,
        Device.usba_output_power,
    ]

    for field_name in power_field_names:
        if field_name in device.updated_fields:
            value = getattr(device, field_name)
            assert isinstance(value, (int, float)), (
                f"Power field {field_name} has wrong type: {type(value)}"
            )


async def test_delta2_plus_maintains_state_across_packets(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    # Check that battery fields were populated
    assert device.battery_level is not None or device.battery_level_main is not None, (
        "No battery level fields were updated"
    )


async def test_delta2_plus_handles_zero_values_correctly(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    # Check that zero power values are handled correctly
    if Device.ac_output_power in device.updated_fields:
        ac_output = device.ac_output_power
        if ac_output is not None and ac_output == 0:
            assert isinstance(ac_output, (int, float))


async def test_delta2_plus_field_types_are_consistent(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    numeric_fields = [
        Device.battery_level,
        Device.battery_level_main,
        Device.battery_1_battery_level,
        Device.input_power,
        Device.output_power,
        Device.ac_output_power,
        Device.ac_input_power,
        Device.ac_input_voltage,
        Device.ac_input_current,
        Device.usbc_output_power,
        Device.usbc2_output_power,
        Device.usba_output_power,
        Device.usba2_output_power,
        Device.cell_temperature,
        Device.dc12v_output_voltage,
        Device.dc12v_output_current,
    ]

    for field_name in numeric_fields:
        value = getattr(device, field_name, None)
        assert isinstance(value, (int, float)), (
            f"Field {field_name} has wrong type: {type(value)}"
        )

    boolean_fields = [
        Device.ac_ports,
        Device.usb_ports,
        Device.dc_12v_port,
        Device.battery_addon,
    ]

    for field_name in boolean_fields:
        value = getattr(device, field_name, None)
        if value is not None:
            assert isinstance(value, (bool, int)), (
                f"Field {field_name} has wrong type: {type(value)}"
            )
            if isinstance(value, int):
                assert value in (0, 1), (
                    f"Boolean field {field_name} has invalid int value"
                )


async def test_delta2_plus_battery_soc_values_are_valid(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    battery_fields = [
        Device.battery_level,
        Device.battery_level_main,
        Device.battery_1_battery_level,
    ]

    for field_name in battery_fields:
        if field_name in device.updated_fields:
            value = getattr(device, field_name)
            assert 0 <= value <= 100, (
                f"{field_name} value {value} is out of valid range (0-100%)"
            )


async def test_delta2_plus_addon_battery_detection(device, packet_sequence):
    assert device.battery_addon is False

    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    if device.battery_1_battery_level is not None:
        assert device.battery_addon is True, (
            "Addon battery not detected after processing battery_1 data"
        )


async def test_delta2_plus_exact_values_from_known_packets(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.battery_level: 99.08,
        Device.battery_level_main: 98.4,
        Device.battery_1_battery_level: 100.0,
        Device.input_power: 437,
        Device.output_power: 318,
        Device.ac_output_power: 318,
        Device.ac_input_power: 437,
        Device.ac_input_voltage: 225.59,
        Device.ac_input_current: 0.49,
        Device.usbc_output_power: 0,
        Device.usba_output_power: 0,
        Device.cell_temperature: 31,
        Device.ac_ports: True,
        Device.usb_ports: False,
        Device.dc_12v_port: False,
        Device.battery_addon: True,
        Device.max_ac_charging_power: 1500,
        Device.remaining_time_charging: 5939,
        Device.remaining_time_discharging: 5939,
    }

    for field_name, expected_value in expected.items():
        actual_value = getattr(device, field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value}, got {actual_value}"
        )

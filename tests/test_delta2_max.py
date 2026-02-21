import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.delta2_max import Device


@pytest.fixture
def packet_sequence():
    """
    Raw packet sequence captured from a Delta 2 Max device

    Packet types cover all main modules:
    - src=0x03, cmdSet=0x20, cmdId=0x32: BmsHeartbeatBatteryMain
    - src=0x03, cmdSet=0x03, cmdId=0x0e: AllKitDetailData
    - src=0x02, cmdSet=0x20, cmdId=0x02: PdHeart
    - src=0x03, cmdSet=0x20, cmdId=0x02: EmsDeltaHeartbeatPack
    - src=0x05, cmdSet=0x20, cmdId=0x02: MpptHeart
    - src=0x04, cmdSet=0x20, cmdId=0x02: InvDeltaHeartbeatPack
    """
    return [
        "aa02c000580efdc7000002510321203200010200000000330101024b26d0000087ffffff1001409c0000bf730000709900000400000064060d040d1210190f0000409c000016df9642000000000000000000000000030000020010050d040d040d040d050d050d040d040d050d050d050d050d060d050d050d050d051000110012001000100056302e312e320301ffff30303030303030303030303030303030510200009642000000004ebc93420600010202000000000000000000ffffffffffffffff00000000000000000000c642fac7",
        "aa025300860c9c77020002510321030e01530002000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000004bf0",
        "aa028900be0cbb000000ffff0221200201000000005a06030100000000004b00000000e1150000010000000000000014140000133c003c00647b11000000000000be1a00006c010000661a000095750000edba0000e4ef00000c0b0000962303007943010000000000000000000001000000008800800000000000000000000000000000000000000000000000ff00000500005005000000005fcc",
        "aa023700270ca5770200025103212002010101f1d70000409c00000064014b01006f170000e115000001e4de964203000001015bcc00002bd400000f0064000000000000000301f20b",
        "aa025c00450cec000000ffff05212002000000005d00000503000000000000000000c7cb0000760000000600120003000000000000000000000000000000000019000000000013000012000000401f00000000000000000000000012000300000000d002401f0000000000000f1c",
        "aa024800460c0d030000ffff04212002000000005b00000200000000000099d20100710000003c000000000000000000120000000000000000001100000100c0d401000200000208072c013c000100000807000000000000ebc6",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.Mock()
    device = Device(ble_dev, adv_data, "R351TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def test_delta2_max_parses_all_packets_successfully(device, packet_sequence):
    expected_packets = [
        (0x03, 0x20, 0x32),  # BmsHeartbeatBatteryMain
        (0x03, 0x03, 0x0E),  # AllKitDetailData
        (0x02, 0x20, 0x02),  # PdHeart
        (0x03, 0x20, 0x02),  # EmsDeltaHeartbeatPack
        (0x05, 0x20, 0x02),  # MpptHeart
        (0x04, 0x20, 0x02),  # InvDeltaHeartbeatPack
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


async def test_delta2_max_processes_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_delta2_max_updates_battery_level(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    battery_fields = [
        Device.battery_level,
        Device.battery_level_main,
    ]

    for field_name in battery_fields:
        value = getattr(device, field_name)
        assert 0 <= value <= 100, f"{field_name} value {value} out of range"


async def test_delta2_max_updates_power_fields(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    assert len(device.updated_fields) > 0, (
        "No fields were updated after processing packets"
    )

    power_field_names = [
        Device.input_power,
        Device.output_power,
        Device.ac_output_power,
        Device.ac_input_power,
        Device.dc_output_power,
    ]

    for field_name in power_field_names:
        value = getattr(device, field_name)
        assert isinstance(value, (int, float)), (
            f"Power field {field_name} has wrong type: {type(value)}"
        )


async def test_delta2_max_handles_zero_values_correctly(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    if Device.ac_output_power in device.updated_fields:
        ac_output = device.ac_output_power
        if ac_output is not None and ac_output == 0:
            assert isinstance(ac_output, (int, float))


async def test_delta2_max_field_types_are_consistent(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    numeric_fields = [
        Device.battery_level,
        Device.battery_level_main,
        Device.input_power,
        Device.output_power,
        Device.ac_output_power,
        Device.ac_input_power,
        Device.ac_input_voltage,
        Device.ac_input_current,
        Device.dc_output_power,
        Device.usbc_output_power,
        Device.usbc2_output_power,
        Device.usba_output_power,
        Device.usba2_output_power,
        Device.cell_temperature,
        Device.dc12v_output_voltage,
        Device.dc12v_output_current,
        Device.ac_charging_speed,
    ]

    for field_name in numeric_fields:
        value = getattr(device, field_name, None)
        if value is not None:
            assert isinstance(value, (int, float)), (
                f"Field {field_name} has wrong type: {type(value)}"
            )

    boolean_fields = [
        Device.ac_ports,
        Device.usb_ports,
        Device.dc_12v_port,
        Device.energy_backup_enabled,
    ]

    for field_name in boolean_fields:
        value = getattr(device, field_name, None)
        assert isinstance(value, (bool, int)), (
            f"Field {field_name} has wrong type: {type(value)}"
        )
        if isinstance(value, int):
            assert value in (0, 1), f"Boolean field {field_name} has invalid int value"


async def test_delta2_max_no_addon_battery(device, packet_sequence):
    assert device.battery_addon is False

    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    assert device.battery_addon is False, (
        "Addon battery incorrectly detected when no battery_1 data present"
    )


async def test_delta2_max_ac_charging_power_limits(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    assert device.max_ac_charging_power == 1800, (
        f"Max AC charging power should be 1800W, got {device.max_ac_charging_power}"
    )


async def test_delta2_max_exact_values_from_known_packets(device, packet_sequence):
    """Test that known packet data produces exact expected values"""
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.battery_level: 75.44,
        Device.battery_level_main: 75.44,
        Device.input_power: 0,
        Device.output_power: 0,
        Device.ac_output_power: 0,
        Device.ac_input_power: 0,
        Device.ac_input_voltage: 0.0,
        Device.ac_input_current: 0.0,
        Device.dc_output_power: 0,
        Device.usbc_output_power: 0,
        Device.usba_output_power: 0,
        Device.cell_temperature: 18,
        Device.ac_ports: True,
        Device.usb_ports: False,
        Device.dc_12v_port: False,
        Device.battery_addon: False,
        Device.max_ac_charging_power: 1800,
        Device.energy_backup_enabled: False,
        Device.ac_charging_speed: 300,
        Device.remaining_time_charging: 5999,
        Device.remaining_time_discharging: 5601,
    }

    for field_name, expected_value in expected.items():
        actual_value = getattr(device, field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value}, got {actual_value}"
        )

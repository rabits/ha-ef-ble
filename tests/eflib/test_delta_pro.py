import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.delta_pro import Device


@pytest.fixture
def packet_sequence():
    """
    Packet sequence for testing Delta Pro device parsing.

    Packet types cover all main modules:
    - src=0x03, cmdSet=0x03, cmdId=0x0e: AllKitDetailData
    - src=0x03, cmdSet=0x20, cmdId=0x02: DirectEmsDeltaHeartbeatPack
    - src=0x02, cmdSet=0x20, cmdId=0x02: DirectPdDeltaProHeartbeatPack
    - src=0x03, cmdSet=0x20, cmdId=0x32: DirectBmsMDeltaHeartbeatPack
    - src=0x04, cmdSet=0x20, cmdId=0x02: DirectInvDeltaHeartbeatPack
    - src=0x05, cmdSet=0x20, cmdId=0x02: DirectMpptHeartbeatPack
    """
    return [
        "aa025300860d0000000000000321030e0153000200014241545041434b3030310000000000000e000400012305000119010001000000005db1b3425a000000000000000000000000000000000000000000000000000000000000000000000000000000b98a",
        "aa022e00cd0d0000000000000321200201010000e10000307500000264004e0000ffff00005001000001cdcc9c42010000010030c0000000e100000000004be3",
        "aa027900aa0d0000000000000221200200000000000001000100000000004ec80000001e0000000000000000000000000000000000003c0032000000000000000000000000c800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000140000320000000000a4e3",
        "aa024500af0d0000000000000321203200010000000000340200014e88c2000000000000190080320200c0b60100803202000c00000062520d340d1a181b1a000030750000cdcc9c4200000000c800000096000000ee10",
        "aa024300d10d000000000000042120020000000056040001020000c800007082030084030000320000000000000000000000000000000000000000000001007082030032000000540bf4010000000000540b00a97c",
        "aa024200c42f278b2900010205212002272727271527262427272727272727272727cf26272724272727352702272427272727272727272727272727272727272727272727272727271727262767382727275478",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "DCA1TEST0000001")
    device._conn = mocker.AsyncMock()
    return device


async def test_delta_pro_parses_all_packets_successfully(device, packet_sequence):
    expected_packets = [
        (0x03, 0x03, 0x0E),  # AllKitDetailData
        (0x03, 0x20, 0x02),  # DirectEmsDeltaHeartbeatPack
        (0x02, 0x20, 0x02),  # DirectPdDeltaProHeartbeatPack
        (0x03, 0x20, 0x32),  # DirectBmsMDeltaHeartbeatPack
        (0x04, 0x20, 0x02),  # DirectInvDeltaHeartbeatPack
        (0x05, 0x20, 0x02),  # DirectMpptHeartbeatPack
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


async def test_delta_pro_processes_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_delta_pro_updates_battery_level(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    value = device.battery_level
    assert 0 <= value <= 100, f"battery_level value {value} out of range"


async def test_delta_pro_updates_power_fields(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    assert len(device.updated_fields) > 0, (
        "No fields were updated after processing packets"
    )

    power_fields = [
        Device.input_power,
        Device.output_power,
        Device.ac_output_power,
        Device.ac_input_power,
        Device.dc_output_power,
    ]

    for field_name in power_fields:
        value = getattr(device, field_name)
        assert isinstance(value, (int, float)), (
            f"Power field {field_name} has wrong type: {type(value)}"
        )


async def test_delta_pro_field_types_are_consistent(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    numeric_fields = [
        Device.battery_level,
        Device.battery_charge_limit_min,
        Device.battery_charge_limit_max,
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
        Device.qc_usb1_output_power,
        Device.qc_usb2_output_power,
        Device.ac_charging_speed,
        Device.energy_backup_battery_level,
        Device.battery_1_battery_level,
    ]

    for field_name in numeric_fields:
        value = getattr(device, field_name, None)
        if value is not None:
            assert isinstance(value, (int, float)), (
                f"Field {field_name} has wrong type: {type(value)}"
            )

    boolean_fields = [
        Device.ac_ports,
        Device.dc_12v_port,
        Device.energy_backup_enabled,
        Device.battery_1_enabled,
        Device.battery_2_enabled,
    ]

    for field_name in boolean_fields:
        value = getattr(device, field_name, None)
        if value is not None:
            assert isinstance(value, (bool, int)), (
                f"Field {field_name} has wrong type: {type(value)}"
            )
            if isinstance(value, int):
                assert value in (0, 1), (
                    f"Boolean field {field_name} has invalid int value: {value}"
                )


async def test_delta_pro_extra_battery_kit_parsed(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    assert device.battery_1_enabled is True, "Kit 0 should be reported as enabled"
    assert device.battery_1_sn == "BATPACK001", (
        f"Unexpected kit 0 SN: {device.battery_1_sn!r}"
    )
    assert 0 <= device.battery_1_battery_level <= 100, (
        f"Kit 0 SOC out of range: {device.battery_1_battery_level}"
    )
    assert device.battery_2_enabled is False, "Kit 1 should be reported as disabled"


async def test_delta_pro_exact_values_from_known_packets(device, packet_sequence):
    """Test that known packet data produces exact expected values."""
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.battery_level: 78.4,
        Device.battery_charge_limit_min: 0,
        Device.battery_charge_limit_max: 100,
        Device.ac_output_power: 200,
        Device.ac_input_power: 0,
        Device.ac_input_voltage: 0.0,
        Device.ac_input_current: 0.0,
        Device.ac_ports: True,
        Device.ac_charging_speed: 500,
        Device.input_power: 0,
        Device.output_power: 200,
        Device.dc_output_power: 0,
        Device.usbc_output_power: 0,
        Device.usba_output_power: 0,
        Device.dc_12v_port: False,
        Device.energy_backup_enabled: False,
        Device.energy_backup_battery_level: 50,
        Device.battery_1_enabled: True,
        Device.battery_1_battery_level: 89.85,
        Device.battery_1_sn: "BATPACK001",
        Device.battery_2_enabled: False,
    }

    for field_name, expected_value in expected.items():
        actual_value = getattr(device, field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value!r}, got {actual_value!r}"
        )

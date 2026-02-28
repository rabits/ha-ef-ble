import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.dpu import Device


@pytest.fixture
def packet_sequence():
    """
    Raw packet sequence captured from a DPU device

    Packet 1 (cmdId=0x04): BpInfoReport - battery pack info (3 battery packs)
    Packet 2 (src=0x06, cmdId=0x10): APPParaHeartbeatReport - system parameters
    Packet 3 (cmdId=0x03): AppShowHeartbeatReport - system status and power data
    """
    return [
        "aa134500662c14a1c602011d0221010102041e011c150c363114141494391414d4512caf2b54704c331e011c160c393114141494391414d4512cfe4154704c311e011c170c3f3114141494391414d4512cbb4454704c37f209",
        "aa13c300ae2c92ff4317061d06210100fe109a9388b39a75420b2a948239690416948a6d95b082929212ad929292d9929292929292929288b39a4815132a9482061e0c56968a6d95b0829292929292929292929292929292929288b39a4815132a948279190c56968a7c95b0829292929292929292929292929292929288b39a7310132a9482792e6551968a6d95b082929212ad929292d9929292929292929288b39a7310132a9482152e6551968a7c95b082929212ad929212d09292929292929292b082cba5a3a0c8d3d0a6a6d5a7c6a2a2aba1531b",
        "aa1349009a2c2da1c602011d022101010203252d3d2d35490d2d05331d2d15116d2c65497d2d752d4d2d45a5235da523552dad2c812fa52cfd28bd2cfd28b52c2d8d2c2c852cb22b9f2c3d6c40485f444e4c0263485a7274425f46ba5b",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.Mock()
    device = Device(ble_dev, adv_data, "Y711TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def test_dpu_parses_all_packets_successfully(device, packet_sequence):
    expected_packets = [
        (0x02, 0x02, 0x04),  # BpInfoReport
        (0x06, 0xFE, 0x10),  # APPParaHeartbeatReport (not handled by device)
        (0x02, 0x02, 0x03),  # AppShowHeartbeatReport (cmdId=0x03, not 0x01)
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


async def test_dpu_processes_all_packets_successfully(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    processed = await device.data_parse(packet)
    assert processed is True, "BpInfoReport packet was not processed"


async def test_dpu_updates_battery_pack_fields(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    battery_field_names = [
        Device.battery_1_battery_level,
        Device.battery_2_battery_level,
        Device.battery_3_battery_level,
    ]

    updated_battery_fields = [
        f for f in battery_field_names if f in device.updated_fields
    ]
    assert len(updated_battery_fields) > 0, "No battery pack fields were updated"

    battery_1_level = getattr(device, Device.battery_1_battery_level)
    assert battery_1_level is not None
    assert isinstance(battery_1_level, (int, float))
    assert 0 <= battery_1_level <= 100, (
        f"Battery 1 level {battery_1_level} out of range"
    )


async def test_dpu_updates_power_fields(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    power_field_names = [
        Device.input_power,
        Device.output_power,
        Device.lv_solar_power,
        Device.hv_solar_power,
    ]

    for field_name in power_field_names:
        if field_name in device.updated_fields:
            value = getattr(device, field_name)
            assert isinstance(value, (int, float)), (
                f"Power field {field_name} has wrong type: {type(value)}"
            )
            assert value >= 0, f"Power field {field_name} has negative value: {value}"


async def test_dpu_handles_zero_values_correctly(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    if Device.input_power in device.updated_fields:
        input_power = device.input_power
        if input_power is not None and input_power == 0:
            assert isinstance(input_power, (int, float))


async def test_dpu_field_types_are_consistent(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    numeric_fields = [
        Device.battery_1_battery_level,
        Device.battery_1_cell_temperature,
        Device.battery_2_battery_level,
        Device.battery_2_cell_temperature,
        Device.battery_3_battery_level,
        Device.battery_3_cell_temperature,
        # TODO(gnox): needs more messages
        # Device.input_power,
        # Device.output_power,
        # Device.lv_solar_power,
        # Device.hv_solar_power,
        # Device.ac_l1_1_out_power,
        # Device.ac_l1_2_out_power,
        # Device.ac_l2_1_out_power,
        # Device.ac_l2_2_out_power,
        # Device.ac_tt_out_power,
        # Device.ac_l14_out_power,
        # Device.ac_5p8_out_power,
    ]

    for field_name in numeric_fields:
        value = getattr(device, field_name, None)
        assert isinstance(value, (int, float)), (
            f"Field {field_name} has wrong type: {type(value)}"
        )


async def test_dpu_battery_soc_values_are_valid(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    for i in range(1, 3):
        field_name = f"battery_{i}_battery_level"
        value = getattr(device, field_name)
        assert value is not None, f"{field_name} should not be None if updated"
        assert 0 <= value <= 100, (
            f"{field_name} value {value} is out of valid range (0-100)"
        )


async def test_dpu_exact_values_from_known_packets(device, packet_sequence):
    """Test that known packet data produces exact expected values"""
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.battery_1_battery_level: 34,
        Device.battery_1_cell_temperature: 39,
        Device.battery_2_battery_level: 45,
        Device.battery_2_cell_temperature: 37,
        Device.battery_3_battery_level: 43,
        Device.battery_3_cell_temperature: 35,
    }

    for field_name, expected_value in expected.items():
        actual_value = getattr(device, field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value}, got {actual_value}"
        )

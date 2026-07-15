import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.delta_pro_3 import DCPortState, Device


@pytest.fixture
def packet_sequence():
    """
    Raw packet sequence captured from a Delta Pro 3 device

    All packets are DisplayPropertyUpload (src=0x02, cmd_set=0xFE, cmd_id=0x15).
    The device alternates between two incremental upload groups: the first packet
    carries battery, power and system status, the second carries port plug-in info
    and flow states.
    """
    return [
        "aa138601b32c078a0502011c02210101fe150f071a0707134422070714442f870637073f0747354a0707070752070707075a0707070762070707076f0977097f098706098f06199706ab059f06d702a706d702cf0607ff06078705078f05079705059a0507070707a20507070707aa0507070707b20507070707ef0507f70507a20407070707aa0407070707b20407071344ba04070714c4c20407070707ca0407070707d20407070707ed000f0d010f0617051f01f50007af0fd905b50f0c46746e662853626f756669bf0f06e70f079f0e06f20e07070707fa0e07070707820d07070707b70c069f0b06c70b079f0a35a70a07af0a07b70a07bf0a079f0905c7090792083a6c6a459a080707cf45c70887f603f708eb46ff08a23497171d9f171aa7171caf1719b2173a6c6a45ba170707cf45e717eb46ef17a234f7173aff17068716138f16349716069f1606cf1607d71607ef1607f716079715971bcd1f07df1f07e71f07ef1f079f1b06a71b57af1b07b71bbf0fbf1b07c71b07df1ba718e71b9704ef1b35f71b87279f1a07a71a07af1a078f19072034",
        "aa130201512cfb890502011c02210101fe150bfafb43f9fb3bf9fe2bf9fb23f9fe03f9f97bf8f973f8fb6bf8fb63f8fb13f8fb0bf8c903f8fb7bfffb73fffb39fefb3bf2f933f2fb2bf2fb23f2fb1bf2fb13f2fb73f1fb6bf1fb63f1fb5bf1fb53f1fb4bf1fb2bf1fb23f1fb5bf0fd53f0eb43f0fb39f0e9f1ebfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb2bf0fb23f0fb19f0e9f1ebfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb0bf0fb03f0fb79f7e9f1ebfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb71f7fb6bf7fb2bf7fa23f7fb1bf7fb13f7fb0bf7fb03f7fb7bf6fb73f66bf86bf657e03bf6fb33f6fb2bf6fb6bf5fb33f5fb2bf5fb23f5f31bf5ef13f55be40bf55be471e0fb33e75be42be72fed7bb4fb73b4fbfa51",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "MR51TEST12345678")
    device._conn = mocker.AsyncMock()
    return device


async def test_delta_pro_3_parses_all_packets_successfully(device, packet_sequence):
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


async def test_delta_pro_3_processes_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_delta_pro_3_exact_values_from_known_packets(device, packet_sequence):
    """Test that known packet data produces exact expected values"""
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.battery_level: 59.35,
        Device.battery_level_main: 59.35,
        Device.state_of_health: 100.0,
        Device.ac_input_power: 148.0,
        Device.ac_lv_output_power: 0.0,
        Device.ac_hv_output_power: 147.0,
        Device.ac_lv_tt30_output_power: 0.0,
        Device.input_power: 148.0,
        Device.output_power: 147.0,
        Device.dc12v_output_power: 0.0,
        Device.usbc_output_power: 0.0,
        Device.usba_output_power: 0.0,
        Device.battery_input_power: 0,
        Device.battery_output_power: 0,
        Device.ac_5p8_in_power: 0.0,
        Device.ac_5p8_out_power: 0.0,
        Device.cell_temperature: 29,
        Device.usb_ports: True,
        Device.dc_12v_port: False,
        Device.ac_lv_port: False,
        Device.ac_hv_port: True,
        Device.plugged_in_ac: True,
        Device.energy_backup: False,
        Device.battery_charge_limit_min: 1,
        Device.battery_charge_limit_max: 61,
        Device.ac_charging_speed: 400,
        Device.max_ac_charging_power: 2900,
        Device.remaining_time_charging: 6565,
        Device.remaining_time_discharging: 8428,
        Device.bms_run_state: True,
        Device.error_code: 0,
        Device.dc_lv_input_power: 0.0,
        Device.dc_hv_input_power: 0.0,
        Device.dc_lv_input_state: DCPortState.STATE_5_UNKNOWN,
        Device.dc_hv_input_state: DCPortState.STATE_5_UNKNOWN,
    }

    for field_name, expected_value in expected.items():
        actual_value = device.get_value(field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value}, got {actual_value}"
        )


async def test_delta_pro_3_computed_fields(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    assert device.error_occurred is False
    assert device.fan_running is False
    assert device.solar_lv_power == 0
    assert device.solar_hv_power == 0


async def test_delta_pro_3_battery_soc_values_are_valid(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    assert device.battery_level is not None
    assert 0 <= device.battery_level <= 100
    assert device.state_of_health is not None
    assert 0 <= device.state_of_health <= 100

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.powerpulse_ev import AcPlugState, Device


@pytest.fixture
def packet_sequence():
    """
    Raw packet sequence captured from a PowerPulse 9.6 kW EV charger (C101)

    Heartbeat packets are src=0x02, cmdSet=0x02, cmdId=0x21 (HeartBeat).
    The charger is idle/unplugged (system_state=1) with line voltage ~239 V.
    """
    return [
        "aa13c400c52dcef301000163022101010221c6cfdccacecececee64e4ecaf4e9c6cedeceebcecececef3cececece8bcececece83cececece9bcececece93cecececeabcececece8cdbc6cfde3a2dcbebcecececef3c532a08d9b32099ef2863a2dcb4ecfcc46cf62cc5ecf5ecd76cfca0bcfcece8e8f06cfaa2bcfcececece24cfcac532a08d3ccfca32099ef234cfccdcdf4ccccccece0ecc0e134700c806cc6fcf1eccbc16cc4c2dcb2ecc3a2dcb26ccce3eccce36ccbc24cdc6c6cedeced6ceeece34cdc4c6cfd4ceeecde6cffefe66c8ce7ec8cecb21",
        "aa13c400c52dd0f301000163022101010221d8d1c2d4d0d0d0d0f85050d4eaf7d8d0c0d0f5d0d0d0d0edd0d0d0d095d0d0d0d09dd0d0d0d085d0d0d0d08dd0d0d0d0b5d0d0d0d092c5d8d1c02433d5f5d0d0d0d0edd2cdbf9385121e81ec982433d550d1d258d17cd240d140d368d1d415d1d0d0909118d1b435d1d0d0d0d03ad1d4d2cdbf9322d1d4121e81ec2ad1d2c2c152d2d2d0d010d2100d591ed618d271d100d2a208d25233d530d22433d538d2d020d2d028d2a23ad3d8d8d0c0d0c8d0f0d02ad3dad8d1cad0f0d3f8d1e0e078d6d060d6d0142c",
        "aa13c400c52dd2f301000163022101010221dad3c0d6d2d2d2d2fa5252d6e8f5dad2c2d2f7d2d2d2d2efd2d2d2d297d2d2d2d29fd2d2d2d287d2d2d2d28fd2d2d2d2b7d2d2d2d290c7dad3c22631d7f7d2d2d2d2ef80d7bd9187101c83ee9a2631d752d3d05ad37ed042d342d16ad3d617d3d2d292931ad3b637d3d2d2d2d238d3d680d7bd9120d3d6101c83ee28d3d0c0c350d0d0d2d212d0120f5b1cd41ad073d302d0a00ad05031d732d02631d73ad0d222d0d22ad0a038d1dadad2c2d2cad2f2d228d1d8dad3c8d2f2d1fad3e2e27ad4d262d4d2d2dd",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "C101N0TEST0342")
    device._conn = mocker.AsyncMock()
    return device


async def test_powerpulse_ev_parses_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))

        assert packet is not None, f"Packet {i} failed to parse"
        assert packet.src == 0x02, f"Packet {i} has unexpected src: {packet.src:#04x}"
        assert packet.cmdSet == 0x02, (
            f"Packet {i} has unexpected cmdSet: {packet.cmdSet:#04x}"
        )
        assert packet.cmdId == 0x21, (
            f"Packet {i} has unexpected cmdId: {packet.cmdId:#04x}"
        )


async def test_powerpulse_ev_processes_all_packets_successfully(
    device, packet_sequence
):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_powerpulse_ev_updates_power_fields(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    power_fields = [
        Device.output_power,
        Device.ac_output_voltage,
        Device.ac_output_current,
    ]

    for field in power_fields:
        value = device.get_value(field)
        assert isinstance(value, (int, float)), (
            f"Power field {field.public_name} has wrong type: {type(value)}"
        )


async def test_powerpulse_ev_field_types_are_consistent(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    numeric_fields = [
        Device.output_power,
        Device.ac_output_voltage,
        Device.ac_output_current,
        Device.total_energy,
    ]

    for field in numeric_fields:
        value = device.get_value(field)
        if value is not None:
            assert isinstance(value, (int, float)), (
                f"Field {field.public_name} has wrong type: {type(value)}"
            )

    assert isinstance(device.get_value(Device.ac_plug_state), AcPlugState)


async def test_powerpulse_ev_exact_values_from_known_packets(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.ac_plug_state: AcPlugState.UNPLUGGED,
        Device.output_power: 0.0,
        Device.ac_output_voltage: 239.0,
        Device.ac_output_current: 0.01,
        Device.total_energy: 94708,
    }

    for field, expected_value in expected.items():
        actual = device.get_value(field)
        assert actual == expected_value, (
            f"{field.public_name}: expected {expected_value}, got {actual}"
        )

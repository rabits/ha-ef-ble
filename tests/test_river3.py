import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.river3 import Device


@pytest.fixture
def packet_sequence():
    """
    Raw packet sequence captured from a River 3 UPS device

    All packets are DisplayPropertyUpload (src=0x02, cmdSet=0xFE, cmdId=0x15)
    containing battery, power, and system status information
    """
    return [
        "aa132c01292c7537e009014502210101fe157d75687575213750757521374d74353e3875757575207575757528757575751075757575fd74d57ee5747fed7475c57475cd747abd7475d87775757575d87675757575c0760c324c37a57175987175757575ed7c74d57c75807c757575b5ed7974ed7847d57875af7875ed7b9374e07a7575e337e87a7575bd37b57af511857aaa688d7a8668e56555ed6554d5656cdd656cc0657575e337c8657575bd379565aa689d65866885652f8d657fed6474bd6475a564759d6475856475ed6375dd6375c56375cd6347b86375757575f0620c324cb7b86f757575758f69257f737d776580847e7f777d767f717d7165557f777d707f717d7365707f777d727f757f757f757f757f757f757f757f757f757f757f757f757f757f757f757f757f757f757f757f757f757f757f757f753e0a",
        "aa135f00b32c7e37e009014502210101fe158e7f7ee67b7ede7b7ed67b7ece7b7ec67b7ebc7b7eb67b7eae7b7ea47b7e9e767e94765d747d76a07a747d76a07a747d76a07a747d76a67d747d76ef7d747e747e747e747e747ed6737ec6737ebe707efc657eee657ede657ece657ec6657e22b0",
        "aa136500c82c8a37e009014502210101fe15e28afa8af28a0a8b8a02888a62888a7a888a72888862898a7a898a7a8e8a728e8a4a83944283945a868b0287b87a8426882a9c8c4a9c8a5a9c8a529c8b6a9c8a629c8a7a9c8a729c8832908a4a908a5a908a52908a6a908a72908a00918a12918a5a963b881f06",
        "aa132c01292c9237e009014502210101fe159a928f9292f2d0b79292f2d0aa93d2d9df92929292c792929292cf92929292f7929292921a9332990293980a93922293922a939d5a93923f90929292923f919292929227913897bdd04296927f96929292920a9b93329b92679b929292520a9e930a9fa0329f92489f920a9c7493079d929204d00f9d92925ad0529d12f6629d4d8f6a9d618f0282b20a82b332828b3a828b2782929204d02f8292925ad072824d8f7a82618f6282c86a82980a83935a83924283927a83926283920a84923a84922284922a84a05f849292929217853897bd505f8892929292688ec298949a908267639998909a9198969a9682b298909a9798969a94829798909a959892989298929892989298929892989298929892989298929892989298929892989298929892989298929892989298928c2e",
        "aa135f00b32c9b37e009014502210101fe156b9a9b039e9b3b9e9b339e9b2b9e9b239e9b599e9b539e9b4b9e9b419e9b7b939b7193b8919893459f919893459f919893459f91989343989198930a98919b919b919b919b919b33969b23969b5b959b19809b0b809b3b809b2b809b23809bbdb3",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.Mock()
    device = Device(ble_dev, adv_data, "R655TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def test_river3_parses_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))

        assert packet is not None, f"Packet {i} failed to parse"
        assert packet.src == 0x02, f"Packet {i} has unexpected src: {packet.src:#04x}"
        assert packet.cmdSet == 0xFE, (
            f"Packet {i} has unexpected cmdSet: {packet.cmdSet:#04x}"
        )
        assert packet.cmdId == 0x15, (
            f"Packet {i} has unexpected cmdId: {packet.cmdId:#04x}"
        )


async def test_river3_processes_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_river3_updates_battery_level(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    assert Device.battery_level in device.updated_fields
    battery_level = getattr(device, Device.battery_level)
    assert battery_level is not None
    assert isinstance(battery_level, (int, float))
    assert 0 <= battery_level <= 100, f"Battery level {battery_level} out of range"


async def test_river3_updates_power_fields(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[0]))
    await device.data_parse(packet)

    power_field_names = [
        Device.ac_input_power,
        Device.ac_output_power,
        Device.input_power,
        Device.output_power,
        Device.dc_input_power,
    ]

    for field_name in power_field_names:
        value = getattr(device, field_name)
        assert isinstance(value, (int, float)), (
            f"Power field {field_name} has wrong type: {type(value)}"
        )


async def test_river3_handles_zero_values_correctly(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    # Check that zero power values are handled correctly
    if Device.ac_output_power in device.updated_fields:
        ac_output = device.ac_output_power
        assert isinstance(ac_output, (int, float))


async def test_river3_field_types_are_consistent(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    numeric_fields = [
        Device.battery_level,
        Device.ac_input_power,
        Device.ac_output_power,
        Device.input_power,
        Device.output_power,
        Device.dc_input_power,
        Device.dc12v_output_power,
        Device.usbc_output_power,
        Device.usba_output_power,
        Device.battery_input_power,
        Device.battery_output_power,
        Device.cell_temperature,
    ]

    for field_name in numeric_fields:
        value = getattr(device, field_name, None)
        if value is not None:
            assert isinstance(value, (int, float)), (
                f"Field {field_name} has wrong type: {type(value)}"
            )

    boolean_fields = [
        Device.plugged_in_ac,
        Device.energy_backup,
        Device.dc_12v_port,
        Device.ac_ports,
    ]

    for field_name in boolean_fields:
        value = getattr(device, field_name, None)
        assert isinstance(value, (bool, int)), (
            f"Field {field_name} has wrong type: {type(value)}"
        )
        if isinstance(value, int):
            assert value in (0, 1), f"Boolean field {field_name} has invalid int value"


async def test_river3_battery_soc_values_are_valid(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    if Device.battery_level in device.updated_fields:
        battery_level = device.battery_level
        assert battery_level is not None
        assert 0 <= battery_level <= 100, (
            f"Battery level {battery_level} is out of valid range (0-100%)"
        )


async def test_river3_energy_calculations(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    # Test that calculated energy fields are computed correctly
    if device.ac_input_energy is not None and device.dc_input_energy is not None:
        assert device.input_energy is not None, (
            "Input energy should be calculated from AC and DC input"
        )
        assert device.input_energy == (
            device.ac_input_energy + device.dc_input_energy
        ), "Input energy calculation is incorrect"

    if (
        device.ac_output_energy is not None
        and device.usba_output_energy is not None
        and device.usbc_output_energy is not None
        and device.dc12v_output_energy is not None
    ):
        assert device.output_energy is not None, (
            "Output energy should be calculated from all output sources"
        )
        expected_output = (
            device.ac_output_energy
            + device.usba_output_energy
            + device.usbc_output_energy
            + device.dc12v_output_energy
        )
        assert device.output_energy == expected_output, (
            "Output energy calculation is incorrect"
        )


async def test_river3_exact_values_from_known_packets(device, packet_sequence):
    """Test that known packet data produces exact expected values"""
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.battery_level: 75.0,
        Device.ac_input_power: 43.76,
        Device.ac_output_power: 43.76,
        Device.input_power: 56.0,
        Device.output_power: 56.0,
        Device.dc_input_power: 0.0,
        Device.dc12v_output_power: 0.0,
        Device.usbc_output_power: 0,
        Device.usba_output_power: 0,
        Device.battery_input_power: 0,
        Device.battery_output_power: 2.0,
        Device.cell_temperature: 33,
        Device.plugged_in_ac: True,
        Device.energy_backup: True,
        Device.dc_12v_port: False,
        Device.ac_ports: True,
        Device.ac_input_energy: 5,
        Device.ac_output_energy: 194805,
        Device.dc_input_energy: 0,
        Device.usbc_output_energy: 32,
        Device.usba_output_energy: 0,
        Device.dc12v_output_energy: 0,
        Device.input_energy: 5,
        Device.output_energy: 194837,
    }

    for field_name, expected_value in expected.items():
        actual_value = getattr(device, field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value}, got {actual_value}"
        )

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.shp2 import Device


@pytest.fixture
def packet_sequence():
    """
    Raw packet sequence captured from an SHP2 device

    Packet 1 (cmd_id=0x01): ProtoTime - timezone, load/backup/watt info
    Packet 2 (cmd_id=0x20): ProtoPushAndSet - battery and channel info
    Packet 3 (cmd_id=0x20): ProtoPushAndSet - location and master info
    Packet 4 (cmd_id=0x20): ProtoPushAndSet - load strategy config
    Packet 5 (cmd_id=0x20): ProtoPushAndSet - circuit 1-7 config
    Packet 6 (cmd_id=0x20): ProtoPushAndSet - circuit 8-12 config
    Packet 7 (cmd_id=0x20): ProtoPushAndSet - final circuit status
    """
    return [
        "aa13ca00130d0100000000000b2101000c010a071000220355544312780d000000000d0000a0410d0000ae420d000022430d000060410d000000000d000040410d000000000d000000000d000000000d000000000d0000b74315d190d83d15192efa3f1536aa923f15a87534401511451d3e154f7ace3d1500a7ed3d150000000015735f6d3e1500000000158f1fcd3e15d38a67401a260d000000000dd909acc30d277693c310be08aa010708ffe40810a709b2010708ffe40810a30922155d000000005dd909acc35d277693c3ad01004029442a06080418022012c6ac",
        "aa13480188010200000004300b2101000c208205c4020ac8010a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a080000000000000000e2030e0800100018002007280730003800ea0310080110011800209f01289f013000381df2031008011001180020c50128c5013000381d10f58501182e2585eb85462d00003a4282052f0a02105110001800200028003000380040004d00000000500058006000680070007800800100880100900100980100bbbb",
        "aa1343011f0d1300000000000b2101000c200878103c18012800306438e8074000480050648a011b54657374204c6f636174696f6e2c20546573742053746174652c2cc8020092058b020ac8010a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000001001187c203c283d308c01388d01800100f50120acf942fd01df66fa428002b3018d021463f84295023b58f7429802b401a502dd2f7940ad02b67c1f40b002002217",
        "aa13fa00ea010a00000004300b2101000c2092051ef501cd2ffb42fd014da7fb428d02fbadf9429502e0d7f842ad02c8d0214058006000800100900100980100a00100a80100b00100b80100c00100c80100d00100e80302f00301f80332980464b00400b804b817d00500d80500e00509e80502f00502f805027801d80100f2014c080120322a04080110012a04080110022a04080110032a04080110042a04080110052a04080110062a04080110072a04080110082a04080110092a040801100a2a040801100b2a040801100c80060288060c900600980600a00632c006b401fa01008202008a02009202009a0200a20200aa0200b20200ba0200c2020080048394c1b8069504000080c0bbbb",
        "aa136701e5010f00000004300b2101000c20920518f501b534fb42fd01feb1fb428d020facf94295025bd3f8428a05c8020ac5020a88010a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a0800000000000000000a000a000a000a000a000a000a000a00180020001200f201170a0408001000103c180122094369726375697420312802fa01170a0408001000103c1801220943697263756974203228048202170a0408001000103c1801220943697263756974203328008a02170a0408001000103c1801220943697263756974203428009a02170a0408001000103c1801220943697263756974203528009a02170a0408001000103c180122094369726375697420362800a202150a0408001000103c18012209436972637569742037bbbb",
        "aa13510162011000000004300b2101000c20920522f501d637fb42fd0134acfb428002b4018d02c8a9f942950217d9f842a50269ae77408a05a8020aa502a202022800aa02170a0408001000103c180122094369726375697420382800b202170a0408001000103c180122094369726375697420392800ba02180a0408001000103c1801220a436972637569742031302800c202180a0408001000103c1801220a436972637569742031312800ca02180a0408001000103c1801220a436972637569742031322800d2050c080110011800200028004000da050c080110011800200028004000e2050c080110011800200028004000ea050c080110011800200028004000f2050c080110011800200028004000fa050c08011001180020002800400082060c0801100118002000280040008a060c08011001180020002800400092060c0801100118002000280040009a060c080110011800200028004000a206020801bbbb",
        "aa134d00ce011400000004300b2101000c20920522f501e82efb42fd016baafb428002b4018d02649ef9429502a8c6f842ad02b67c1f408a05250a239a06024000a2060c080110011800200028004000aa060c080110011800200028004000bbbb",
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.Mock()
    device = Device(ble_dev, adv_data, "HD31TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def test_shp2_parses_all_packets_successfully(device, packet_sequence):
    expected_cmd_ids = [0x01, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20]

    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        assert packet is not None, f"Packet {i} failed to parse"
        assert packet.src == 0x0B, f"Packet {i} has unexpected src"
        assert packet.cmdSet == 0x0C, f"Packet {i} has unexpected cmdSet"
        assert packet.cmdId == expected_cmd_ids[i], (
            f"Packet {i} has unexpected cmdId: 0x{packet.cmdId:02x}"
        )


async def test_shp2_processes_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_shp2_updates_battery_level(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[1]))
    await device.data_parse(packet)

    assert Device.battery_level in device.updated_fields
    battery_level = getattr(device, Device.battery_level)
    assert battery_level is not None
    assert isinstance(battery_level, (int, float))
    assert 0 <= battery_level <= 100, f"Battery level {battery_level} out of range"


async def test_shp2_updates_channel_fields(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[1]))
    await device.data_parse(packet)

    channel_field_names = [
        Device.channel1_is_enabled,
        Device.channel1_is_connected,
        Device.channel2_is_enabled,
        Device.channel2_is_connected,
        Device.channel3_is_enabled,
        Device.channel3_is_connected,
    ]

    updated_channel_fields = [
        f for f in channel_field_names if f in device.updated_fields
    ]
    assert len(updated_channel_fields) > 0, "No channel fields were updated"


async def test_shp2_maintains_state_across_packets(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    battery_level = device.battery_level
    assert battery_level is not None

    error_count = device.error_count
    assert error_count is not None


async def test_shp2_handles_zero_values_correctly(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[1]))
    await device.data_parse(packet)

    error_count = device.error_count
    if error_count is not None and error_count == 0:
        assert isinstance(error_count, int)


async def test_shp2_field_types_are_consistent(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    numeric_fields = [Device.battery_level]

    for field_name in numeric_fields:
        value = getattr(device, field_name, None)
        if value is not None:
            assert isinstance(value, (int, float)), (
                f"Field {field_name} has wrong type: {type(value)}"
            )

    boolean_fields = [
        f"channel{i}_is_enabled" for i in range(1, Device.NUM_OF_CHANNELS + 1)
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


async def test_shp2_exact_values_from_known_packets(device, packet_sequence):
    """Test that known packet data produces exact expected values"""
    # Process first two packets
    for hex_packet in packet_sequence[:2]:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.battery_level: 46,
        Device.channel1_is_enabled: 0,
        Device.channel1_is_connected: 0,
        Device.ch1_ctrl_status: 0,
        Device.ch2_ctrl_status: 1,
        Device.ch3_ctrl_status: 1,
        Device.ch1_backup_is_ready: False,
        Device.ch2_backup_is_ready: True,
        Device.ch3_backup_is_ready: True,
        Device.error_count: 0,
        Device.error_happened: True,
    }

    for field_name, expected_value in expected.items():
        actual_value = getattr(device, field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value}, got {actual_value}"
        )

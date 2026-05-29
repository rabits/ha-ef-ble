import logging

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.shp2 import Device
from custom_components.ef_ble.eflib.packet import Packet
from custom_components.ef_ble.eflib.pb import pd303_pb2
from custom_components.ef_ble.eflib.props import FieldGroup


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
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "HD31TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def test_shp2_parses_all_packets_successfully(device, packet_sequence):
    expected_cmd_ids = [0x01, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20]

    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        assert packet is not None, f"Packet {i} failed to parse"
        assert packet.src == 0x0B, f"Packet {i} has unexpected src"
        assert packet.cmd_set == 0x0C, f"Packet {i} has unexpected cmd_set"
        assert packet.cmd_id == expected_cmd_ids[i], (
            f"Packet {i} has unexpected cmd_id: 0x{packet.cmd_id:02x}"
        )


async def test_shp2_processes_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        processed = await device.data_parse(packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_shp2_updates_battery_level(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[1]))
    await device.data_parse(packet)

    assert Device.battery_level.public_name in device.updated_fields
    battery_level = device.get_value(Device.battery_level)
    assert battery_level is not None
    assert isinstance(battery_level, (int, float))
    assert 0 <= battery_level <= 100, f"Battery level {battery_level} out of range"


async def test_shp2_updates_channel_fields(device, packet_sequence):
    packet = await device.packet_parse(bytes.fromhex(packet_sequence[1]))
    await device.data_parse(packet)

    channel_field_names = [
        Device.channel_is_enabled[1],
        Device.channel_is_connected[1],
        Device.channel_is_enabled[2],
        Device.channel_is_connected[2],
        Device.channel_is_enabled[3],
        Device.channel_is_connected[3],
    ]

    updated_channel_fields = [
        f.public_name
        for f in channel_field_names
        if f.public_name in device.updated_fields
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


def _backup_incre_packet(*err_codes: bytes) -> Packet:
    """A backup_incre_info (0x0B/0x0C/0x20) packet carrying the given errcodes."""
    message = pd303_pb2.ProtoPushAndSet()
    message.backup_incre_info.errcode.err_code.extend(err_codes)
    return Packet(0x0B, 0x21, 0x0C, 0x20, message.SerializeToString())


async def test_shp2_empty_errcode_is_not_an_error(device, caplog):
    zero = b"\x00" * 8
    with caplog.at_level(logging.WARNING):
        await device.data_parse(_backup_incre_packet(zero))

    assert device.error_count == 0
    assert device.error_happened is False
    assert "Error happened on device" not in caplog.text


async def test_shp2_real_error_warns_then_clears(device, caplog):
    err = b"\x01\x00\x00\x00\x00\x00\x00\x00"

    pushed: list[bool] = []
    device.register_state_update_callback(pushed.append, "error_happened")

    with caplog.at_level(logging.WARNING):
        await device.data_parse(_backup_incre_packet(err))
    assert device.error_count == 1
    assert device.error_happened is True
    assert "Error happened on device" in caplog.text

    # error clears -> problem turns off and no new warning is logged
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        await device.data_parse(_backup_incre_packet(b"\x00" * 8))
    assert device.error_count == 0
    assert device.error_happened is False
    assert "Error happened on device" not in caplog.text

    assert pushed == [True, False]


async def test_shp2_field_types_are_consistent(device, packet_sequence):
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    numeric_fields = [Device.battery_level]

    for field_name in numeric_fields:
        value = device.get_value(field_name)
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
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    expected = {
        Device.battery_level: 46,
        Device.in_use_power: 677.0,
        Device.storm_mode: False,
        Device.error_count: 0,
        Device.error_happened: False,
        Device.channel_power[1]: 0.0,
        Device.channel_power[2]: -344.08,
        Device.channel_power[3]: -294.92,
        Device.circuit_power[1]: 0.0,
        Device.circuit_power[2]: 20.0,
        Device.circuit_power[12]: 366.0,
        Device.circuit_current[1]: 0.1057,
        Device.circuit_current[2]: 1.9545,
        Device.circuit_current[12]: 3.6178,
        Device.channel_output_power[1]: 0.0,
        Device.channel_battery_percentage[1]: 0,
        Device.channel_battery_temp[1]: 0,
        Device.channel_lcd_input[1]: 0,
        Device.channel_pv_lv_input[1]: 0,
        Device.channel_pv_hv_input[1]: 0,
        Device.channel_error_code[1]: 0,
        Device.channel_is_enabled[1]: 0,
        Device.channel_is_connected[1]: 0,
        Device.channel_is_ac_open[1]: 0,
        Device.channel_is_power_output[1]: 0,
        Device.channel_is_grid_charge[1]: 0,
        Device.channel_is_mppt_charge[1]: 0,
        Device.channel_ems_charging[1]: 0,
        Device.channel_hw_connect[1]: 0,
        Device.ch_ctrl_status[1]: 0,
        Device.ch_ctrl_status[2]: 1,
        Device.ch_ctrl_status[3]: 1,
        Device.ch_backup_is_ready[1]: False,
        Device.ch_backup_is_ready[2]: True,
        Device.ch_backup_is_ready[3]: True,
        Device.ch_force_charge[1]: 0,
        Device.ch_force_charge[2]: 0,
        Device.ch_force_charge[3]: 0,
        Device.ch_backup_rly1_cnt[1]: 7,
        Device.ch_backup_rly1_cnt[2]: 159,
        Device.ch_backup_rly1_cnt[3]: 197,
        Device.ch_backup_rly2_cnt[1]: 7,
        Device.ch_backup_rly2_cnt[2]: 159,
        Device.ch_backup_rly2_cnt[3]: 197,
        Device.ch_wake_up_charge_status[1]: 0,
        Device.ch_5p8_type[1]: 0,
        Device.ch_5p8_type[2]: 29,
        Device.ch_5p8_type[3]: 29,
    }

    for field, expected_value in expected.items():
        actual_value = device.get_value(field)
        assert actual_value == expected_value, (
            f"{field.public_name}: expected {expected_value}, got {actual_value}"
        )


def test_shp2_field_group_are_expanded_and_renamed():
    expected_names = {
        *(f"circuit_power_{i}" for i in range(1, 13)),
        *(f"circuit_current_{i}" for i in range(1, 13)),
        *(f"channel_power_{i}" for i in range(1, 4)),
        *(f"circuit_{i}" for i in range(1, 13)),
        *(f"circuit_split_link_{i}" for i in range(1, 13)),
        *(f"circuit_split_info_loaded_{i}" for i in range(1, 13)),
        *(
            f"channel{i}_{suffix}"
            for i in range(1, 4)
            for suffix in [
                "sn",
                "type",
                "capacity",
                "rate_power",
                "is_enabled",
                "is_connected",
                "is_ac_open",
                "is_power_output",
                "is_grid_charge",
                "is_mppt_charge",
                "battery_percentage",
                "output_power",
                "ems_charging",
                "hw_connect",
                "battery_temp",
                "lcd_input",
                "pv_status",
                "pv_lv_input",
                "pv_hv_input",
                "error_code",
            ]
        ),
        *(
            f"ch{i}_{suffix}"
            for i in range(1, 4)
            for suffix in [
                "backup_is_ready",
                "ctrl_status",
                "force_charge",
                "backup_rly1_cnt",
                "backup_rly2_cnt",
                "wake_up_charge_status",
                "5p8_type",
            ]
        ),
    }

    actual_names: set[str] = set()
    for attr_name in dir(Device):
        attr = getattr(Device, attr_name, None)
        if isinstance(attr, FieldGroup):
            for field in attr:
                actual_names.add(field.public_name)

    assert actual_names == expected_names

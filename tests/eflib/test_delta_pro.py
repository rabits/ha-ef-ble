import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.delta_pro import Device
from custom_components.ef_ble.eflib.model import (
    DirectBmsMDeltaHeartbeatPack,
    DirectInvDeltaHeartbeatPack,
    DirectMpptHeartbeatPack,
)
from custom_components.ef_ble.eflib.model.base import RawData
from custom_components.ef_ble.eflib.packet import Packet

# Index of each heartbeat in `packet_sequence`, with its source address and model
_BMS = (3, 0x03, DirectBmsMDeltaHeartbeatPack)


def _reference(packet_sequence, kind: tuple[int, int, type[RawData]], **fields):
    """The decoded reference heartbeat of `kind`, with `fields` replaced"""
    index, _, model = kind
    reference = Packet.from_bytes(
        bytes.fromhex(packet_sequence[index]), xor_payload=True
    )
    data = model.from_bytes(reference.payload)
    for name, value in fields.items():
        setattr(data, name, value)
    return data


def _heartbeat(
    packet_sequence,
    kind: tuple[int, int, type[RawData]],
    src: int | None = None,
    **fields,
) -> Packet:
    """The reference heartbeat with `fields` replaced, as the device would send it"""
    index, kind_src, _ = kind
    reference = Packet.from_bytes(
        bytes.fromhex(packet_sequence[index]), xor_payload=True
    )
    return Packet(
        kind_src if src is None else src,
        0x21,
        reference.cmd_set,
        reference.cmd_id,
        _reference(packet_sequence, kind, **fields).pack(),
        version=0x02,
    )


@pytest.fixture
def packet_sequence():
    """
    Packet sequence for testing Delta Pro device parsing.

    Packet types cover all main modules:
    - src=0x03, cmd_set=0x03, cmd_id=0x0e: AllKitDetailData
    - src=0x03, cmd_set=0x20, cmd_id=0x02: DirectEmsDeltaHeartbeatPack
    - src=0x02, cmd_set=0x20, cmd_id=0x02: DirectPdDeltaProHeartbeatPack
    - src=0x03, cmd_set=0x20, cmd_id=0x32: DirectBmsMDeltaHeartbeatPack
    - src=0x04, cmd_set=0x20, cmd_id=0x02: DirectInvDeltaHeartbeatPack
    - src=0x05, cmd_set=0x20, cmd_id=0x02: DirectMpptHeartbeatPack
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
        expected_src, expected_cmd_set, expected_cmd_id = expected_packets[i]

        assert packet is not None, f"Packet {i} failed to parse"
        assert packet.src == expected_src, (
            f"Packet {i} has unexpected src: {packet.src:#04x} != {expected_src:#04x}"
        )
        assert packet.cmd_set == expected_cmd_set, (
            f"Packet {i} has unexpected cmd_set: "
            f"{packet.cmd_set:#04x} != {expected_cmd_set:#04x}"
        )
        assert packet.cmd_id == expected_cmd_id, (
            f"Packet {i} has unexpected cmd_id: "
            f"{packet.cmd_id:#04x} != {expected_cmd_id:#04x}"
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
        value = device.get_value(field_name)
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
        value = device.get_value(field_name)
        if value is not None:
            assert isinstance(value, (int, float)), (
                f"Field {field_name} has wrong type: {type(value)}"
            )

    boolean_fields = [
        Device.ac_ports,
        Device.dc_12v_port,
        Device.energy_backup,
        Device.battery_1_enabled,
        Device.battery_2_enabled,
    ]

    for field_name in boolean_fields:
        value = device.get_value(field_name)
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
        Device.ac_charging_power_max: 2900,
        Device.input_power: 0,
        Device.output_power: 200,
        Device.dc_output_power: 0,
        Device.usbc_output_power: 0,
        Device.usba_output_power: 0,
        Device.dc_12v_port: False,
        Device.energy_backup: False,
        Device.energy_backup_battery_level: 50,
        Device.battery_1_enabled: True,
        Device.battery_1_battery_level: 89.85,
        Device.battery_1_sn: "BATPACK001",
        Device.battery_2_enabled: False,
        Device.remaining_time_charging: 65535,
        Device.remaining_time_discharging: 336,
        Device.battery_level_main: 78.4,
        Device.battery_voltage: 49.8,
        Device.max_cell_voltage: 3.41,
        Device.min_cell_voltage: 3.38,
        Device.battery_temperature: 25,
        Device.cell_temperature: 26,
        Device.state_of_health: 98,
        Device.battery_remaining_capacity: 112320,
        Device.battery_full_capacity: 144000,
        Device.battery_cycles: 12,
        Device.battery_current: 0.0,
        Device.battery_input_power: 0,
        Device.battery_output_power: 0,
        Device.ac_output_voltage: 230.0,
    }

    for field_name, expected_value in expected.items():
        actual_value = device.get_value(field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value!r}, got {actual_value!r}"
        )


@pytest.mark.parametrize(
    ("raw_attr", "raw_value", "field_name", "expected"),
    [
        ("car_out_watts", 60, Device.dc_output_power, 6.0),
        ("dcdc_12v_watts", 138, Device.anderson_out_power, 138),
    ],
    ids=["dc_output_power", "anderson_out_power"],
)
async def test_delta_pro_mppt_output_power_scale(
    device, packet_sequence, raw_attr, raw_value, field_name, expected
):
    """12 V car output is in tenths of a watt, the Anderson output in whole watts"""
    for hex_packet in packet_sequence:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)

    mppt = DirectMpptHeartbeatPack.from_bytes(packet.payload)
    setattr(mppt, raw_attr, raw_value)
    device.update_from_data(mppt)

    assert device.get_value(field_name) == expected


async def test_delta_pro_charging_ceiling_covers_a_230v_unit_without_rated_power(
    device, packet_sequence
):
    """A 230 V unit can report no rated power while it charges at 2600 W"""
    reference = await device.packet_parse(bytes.fromhex(packet_sequence[4]))
    inv = DirectInvDeltaHeartbeatPack.from_bytes(reference.payload)
    inv.cfg_ac_out_voltage = 230_000
    inv.cfg_slow_chg_watts = 2600
    inv.ac_chg_rated_power = 0
    packet = Packet(0x04, 0x21, 0x20, 0x02, inv.pack(), version=0x02)

    assert await device.data_parse(packet)

    assert device.ac_charging_speed == 2600
    assert device.ac_charging_power_max >= 2600


@pytest.mark.parametrize("num", [1, 2])
async def test_delta_pro_extra_battery_heartbeat_fills_only_its_own_slot(
    device, packet_sequence, num
):
    packet = _heartbeat(
        packet_sequence,
        _BMS,
        src=0x06,
        num=num,
        max_cell_temp=30,
        vol=51_230,
        max_cell_vol=3_420,
        min_cell_vol=3_401,
        input_watts=922,
        output_watts=37,
        remain_cap=70_001,
        full_cap=79_360,
        cycles=72,
    )

    assert await device.data_parse(packet)

    expected = {
        "cell_temperature": 30,
        "voltage": 51.23,
        "max_cell_voltage": 3.42,
        "min_cell_voltage": 3.401,
        "input_power": 922,
        "output_power": 37,
        "remaining_capacity": 70_001,
        "full_capacity": 79_360,
        "cycles": 72,
    }
    for name, value in expected.items():
        assert device.get_value(f"battery_{num}_{name}") == value, name
        assert device.get_value(f"battery_{3 - num}_{name}") is None, name
    assert device.get_value(Device.cell_temperature) is None
    assert device.get_value(Device.battery_level_main) is None


async def test_delta_pro_main_pack_heartbeat_does_not_fill_an_extra_battery(
    device, packet_sequence
):
    assert await device.data_parse(_heartbeat(packet_sequence, _BMS))

    assert device.get_value(Device.cell_temperature) == 26
    assert device.get_value(Device.battery_level_main) == 78.4
    assert device.get_value(Device.battery_level) is None
    assert device.get_value(Device.battery_1_cell_temperature) is None
    assert device.get_value(Device.battery_2_cell_temperature) is None


@pytest.mark.parametrize(
    ("amp", "expected"),
    [
        (6_481, 6.48),
        ((1 << 32) - 6_481, -6.48),
        ((1 << 31) - 1, 2_147_483.65),
        (1 << 31, -2_147_483.65),
    ],
    ids=["charging", "discharging", "int32_max", "int32_min"],
)
async def test_delta_pro_battery_current_is_signed(
    device, packet_sequence, amp, expected
):
    assert await device.data_parse(_heartbeat(packet_sequence, _BMS, amp=amp))

    assert device.battery_current == expected


@pytest.mark.parametrize(
    ("amp", "input_power", "output_power"),
    [
        (12_340, 614.0, 0),
        (0, 0, 0),
        ((1 << 32) - 6_481, 0, 322.4),
    ],
    ids=["charging", "idle", "discharging"],
)
async def test_delta_pro_battery_power_splits_by_direction(
    device, packet_sequence, amp, input_power, output_power
):
    """The power comes from volts × amps, as a main pack can send 0 watts both ways"""
    packet = _heartbeat(packet_sequence, _BMS, vol=49_762, amp=amp)

    assert await device.data_parse(packet)

    assert device.battery_input_power == input_power
    assert device.battery_output_power == output_power


async def test_delta_pro_unknown_pack_slot_is_left_unprocessed(device, packet_sequence):
    packet = _heartbeat(packet_sequence, _BMS, src=0x06, num=5)

    assert not await device.data_parse(packet)

    assert device.get_value(Device.battery_1_cell_temperature) is None
    assert device.get_value(Device.battery_2_cell_temperature) is None

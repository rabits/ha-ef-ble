import struct

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.powerpulse_ev import AcPlugState, Device
from custom_components.ef_ble.eflib.packet import Packet


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "C101N0TEST0342")
    device._conn = mocker.AsyncMock()
    return device


def test_powerpulse_ev_check_only_c101():
    assert Device.check(b"C101XXXX") is True
    assert Device.check(b"C371XXXX") is False
    assert Device.check(b"AC71XXXX") is False


def test_powerpulse_ev_device_name_for_c101(device: Device):
    assert "9.6 kW" in device.device


async def test_powerpulse_ev_ignores_other_packet_sources(device: Device):
    packet = Packet(
        src=0x14,
        dst=0x20,
        cmd_set=0x02,
        cmd_id=0x21,
        payload=b"",
    )
    processed = await device.data_parse(packet)
    assert processed is False


async def test_powerpulse_ev_cmdset2_status_packet_defaults_unknown_values_to_zero(
    device: Device,
):
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x02,
        cmd_id=0x21,
        payload=b"",
    )
    processed = await device.data_parse(packet)
    assert processed is True
    assert device.get_value(Device.ac_output_voltage) == 0.0
    assert device.get_value(Device.ac_output_current) == 0.0
    assert device.get_value(Device.output_power) == 0.0
    assert device.get_value(Device.ac_plug_state) == AcPlugState.UNKNOWN


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            return bytes(out)


def _wire_float_field(field_number: int, value: float) -> bytes:
    key = (field_number << 3) | 5
    return _encode_varint(key) + struct.pack("<f", value)


def _cmd_2_2_33_payload(
    power_w: float,
    voltage_v: float,
    current_a: float,
    *,
    state: int = 2,
) -> bytes:
    nested = (
        _wire_float_field(4, power_w)
        + _wire_float_field(7, voltage_v)
        + _wire_float_field(10, current_a)
    )
    # top-level field #1 (varint) tracks charger state on C101 logs
    # 1=unplugged, 2=plugged idle, 3=charging, 6=charge complete.
    state_field = _encode_varint((1 << 3) | 0) + _encode_varint(state)
    top_key = _encode_varint((8 << 3) | 2)
    return state_field + top_key + _encode_varint(len(nested)) + nested


async def test_powerpulse_ev_cmdset2_status_packet_parses_nested_metrics(
    device: Device,
):
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x02,
        cmd_id=0x21,
        payload=_cmd_2_2_33_payload(
            power_w=4320.7,
            voltage_v=238.9,
            current_a=18.53,
            state=3,
        ),
    )
    processed = await device.data_parse(packet)
    assert processed is True
    assert device.get_value(Device.ac_output_voltage) == 238.9
    assert device.get_value(Device.ac_output_current) == 18.53
    assert device.get_value(Device.output_power) == 4320.7
    assert device.get_value(Device.ac_plug_state) == AcPlugState.CHARGING


@pytest.mark.parametrize(
    (
        "power_w",
        "voltage_v",
        "current_a",
        "expected_voltage",
        "expected_current",
        "expected_power",
    ),
    [
        # Car plugged in but not charging: voltage present, current/power are near zero.
        (0.0, 239.2, 0.0, 239.2, 0.0, 0.0),
        # Transition phase observed in logs: roughly 1.28 kW and ~6 A.
        (1283.6, 239.1, 5.80, 239.1, 5.8, 1283.6),
        # Higher load observed in logs: roughly 4.33 kW and ~18.5 A.
        (4330.2, 238.8, 18.52, 238.8, 18.52, 4330.2),
    ],
)
async def test_powerpulse_ev_cmdset2_status_packet_maps_representative_log_values(
    device: Device,
    power_w: float,
    voltage_v: float,
    current_a: float,
    expected_voltage: float,
    expected_current: float,
    expected_power: float,
):
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x02,
        cmd_id=0x21,
        payload=_cmd_2_2_33_payload(
            power_w=power_w,
            voltage_v=voltage_v,
            current_a=current_a,
        ),
    )
    processed = await device.data_parse(packet)
    assert processed is True

    # Expected voltage from nested field 7, rounded to 0.1V.
    assert device.get_value(Device.ac_output_voltage) == expected_voltage
    # Expected current from nested field 10, rounded to 0.01A.
    assert device.get_value(Device.ac_output_current) == expected_current
    # Expected charging power from nested field 4, rounded to 0.1W.
    assert device.get_value(Device.output_power) == expected_power


async def test_powerpulse_ev_cmdset2_status_packet_clamps_idle_noise_to_zero(
    device: Device,
):
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x02,
        cmd_id=0x21,
        payload=_cmd_2_2_33_payload(power_w=0.2, voltage_v=239.2, current_a=0.0125),
    )
    processed = await device.data_parse(packet)
    assert processed is True
    # Voltage should still report line voltage while idle.
    assert device.get_value(Device.ac_output_voltage) == 239.2
    # Near-zero telemetry noise is clamped to 0 for user-facing idle state.
    assert device.get_value(Device.ac_output_current) == 0.0
    assert device.get_value(Device.output_power) == 0.0
    assert device.get_value(Device.ac_plug_state) == AcPlugState.PLUGGED_IN


async def test_powerpulse_ev_handles_time_sync_request(
    device: Device, mocker: MockerFixture
):
    mocker.patch.object(device._time_commands, "async_send_all")
    packet = Packet(
        src=0x35,
        dst=0x20,
        cmd_set=0x01,
        cmd_id=Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME,
        payload=b"",
    )
    processed = await device.data_parse(packet)
    assert processed is True
    device._time_commands.async_send_all.assert_called_once()


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        # Logged after charge-complete transition when cable is unplugged.
        (1, AcPlugState.UNPLUGGED),
        # Logged as plugged in but not charging.
        (2, AcPlugState.PLUGGED_IN),
        # Logged during active charging.
        (3, AcPlugState.CHARGING),
        # Logged after charging session ended with cable still connected.
        (6, AcPlugState.CHARGE_COMPLETE),
    ],
)
async def test_powerpulse_ev_cmdset2_status_packet_sets_plugged_in_state(
    device: Device, state: int, expected: AcPlugState
):
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x02,
        cmd_id=0x21,
        payload=_cmd_2_2_33_payload(
            power_w=0.0,
            voltage_v=239.0,
            current_a=0.0,
            state=state,
        ),
    )
    processed = await device.data_parse(packet)
    assert processed is True
    assert device.get_value(Device.ac_plug_state) == expected


async def test_powerpulse_ev_cmdset2_status_packet_charge_complete_maps_from_logs(
    device: Device,
):
    # Representative post-charge-complete frame from logs:
    # top-level state=6, AC voltage present, current near zero.
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x02,
        cmd_id=0x21,
        payload=_cmd_2_2_33_payload(
            power_w=0.0,
            voltage_v=239.0,
            current_a=0.0125,
            state=6,
        ),
    )
    processed = await device.data_parse(packet)
    assert processed is True
    assert device.get_value(Device.ac_plug_state) == AcPlugState.CHARGE_COMPLETE
    # Near-zero current and power are clamped for idle/complete state readability.
    assert device.get_value(Device.ac_output_current) == 0.0


async def test_powerpulse_ev_cmdset2_status_packet_unplugged_maps_from_logs(
    device: Device,
):
    # Representative unplugged frame from logs:
    # top-level state transitions to 1 after charge-complete period.
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x02,
        cmd_id=0x21,
        payload=_cmd_2_2_33_payload(
            power_w=0.0,
            voltage_v=239.0,
            current_a=0.0,
            state=1,
        ),
    )
    processed = await device.data_parse(packet)
    assert processed is True
    assert device.get_value(Device.ac_plug_state) == AcPlugState.UNPLUGGED


async def test_powerpulse_ev_packet_parse_roundtrip_xor(device: Device):
    payload = _cmd_2_2_33_payload(
        power_w=500.0,
        voltage_v=238.5,
        current_a=2.1,
        state=3,
    )
    inner = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0x02,
        cmd_id=0x21,
        payload=payload,
        seq=b"\x00\x00\x00\x00",
    )
    raw = inner.toBytes()
    parsed = await device.packet_parse(raw)
    assert not Packet.is_invalid(parsed)
    assert parsed.src == 0x02
    assert parsed.cmdSet == 0x02
    assert parsed.cmdId == 0x21
    processed = await device.data_parse(parsed)
    assert processed is True
    assert device.get_value(Device.ac_plug_state) == AcPlugState.CHARGING
    assert device.get_value(Device.output_power) == 500.0

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib import controls, units
from custom_components.ef_ble.eflib.devices.wave2 import (
    Device,
    DrainMode,
    FanGear,
    MainMode,
    PowerMode,
    SubMode,
    WaterLevel,
)

PACKETS = {
    "fan_celsius_target_30": "aa026c00bc2de6b30200012d42214250e4e5f8e45a3990a7e6ece6e7e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e4e7e7e7e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e66d8b9fa7e6e6e4e6e6e6e7e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e6e671a6",
    "heat_celsius_target_30": "aa026c00bc2df8b30200012d42214250f9fbe6fa176d8fb9f8f2f8f9f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8faf9f9f9f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f40681b9f8f8faf8f8f8f9f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8f8b664",
    "heat_celsius_target_16": "aa026c00bc2d2db40200012d422142502c2e3d2f2200ad6c2d272d2c2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2f2c2c2c682d2d2d2d2d2d2d2d2d2d2d2d2d2d2d6b9f576c2d2d2f2d2d2d2c2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d1cd3",
    "fan_fahrenheit_target_86": "aa026c00bc2d7bb40200012d4221425079782d794ab40c397a717b7a7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b797a7a7a7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b63470f397b7b797b7b7b7a7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7b7bc4ac",
    "heat_fahrenheit_target_86": "aa026c00bc2d91b40200012d422142509092c79361a6e8d3909b91909191919191919191919191919191919191919191919191919191919191919191919191919191919191919191919390909091919191919191919191919191919191fb14e2d391919391919190919191919191919191919191919191919191919158e2",
    "heat_drain_off_external": "aa026c00bc2dadb40200012d42214250acae91af6df8d7efaca7adacadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadafacacacacadadadadadadadadadadadadadadad5ff9d9efadadafadadadacadadadadadadadadadadadadadadadadadadadad8c09",
    "fan_fahrenheit_target_60": "aa026c00bc2de7b40200012d42214250e5e4dbe591069da5e6ede7e6e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e5e6e6e6e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7fd3e93a5e7e7e5e7e7e7e6e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7e793e2",
    "heat_drain_wte_zero": "aa026c00bc2d18b50200012d42214250191b241a57fd645a19121819181818181818181818181818181818181818181818181818181818181818181818181818181818181818181818181919191a18181818181818181818181818181828156f5a18181a1818181918181818181818181818181818181818181818181fdd",
    "heat_drain_on": "aa026c00bc2d2fb50200012d422142502e2c132de488526d2e252f2e2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2e2e2e2e2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f1f22586d2f2f2d2f2f2f2e2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2fa354",
    "heat_drain_off_drain_free": "aa026c00bc2d66b50200012d4221425067655a6486c91b24676c6667666666666666666666666666666666666666666666666666666666666666666666666666666666666666666666656767676666666666666666666666666666666663da10246666646666666766666666666666666666666666666666666666668151",
    "heat_fahrenheit_standby": "aa026c00bc2da5b50200012d42214250a4a699a7e7dcdbe7a4afa5a4a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a7a4a7a4a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5550bd2e7a5a5a7a5a5a5a4a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5f338",
}


@pytest.fixture
def packet_sequence():
    return list(PACKETS.values())


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "KT21TEST1234")
    device._conn = mocker.AsyncMock()
    return device


async def _process(device: Device, hex_packet: str) -> bool:
    packet = await device.packet_parse(bytes.fromhex(hex_packet))
    assert packet is not None
    return await device.data_parse(packet)


def _sent_drain_payload(device: Device) -> bytes:
    packet = device._conn.send_packet.call_args.args[0]
    assert packet.cmd_id == 0x59
    return packet.payload


async def test_wave2_parses_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))

        assert packet is not None, f"Packet {i} failed to parse"
        assert packet.src == 0x42, f"Packet {i} has unexpected src: {packet.src:#04x}"
        assert packet.cmd_set == 0x42, (
            f"Packet {i} has unexpected cmd_set: {packet.cmd_set:#04x}"
        )
        assert packet.cmd_id == 0x50, (
            f"Packet {i} has unexpected cmd_id: {packet.cmd_id:#04x}"
        )


async def test_wave2_processes_all_packets_successfully(device, packet_sequence):
    for i, hex_packet in enumerate(packet_sequence):
        processed = await _process(device, hex_packet)
        assert processed is True, f"Packet {i} was not processed"


async def test_wave2_exact_values_from_known_packets(device, packet_sequence):
    for hex_packet in packet_sequence:
        await _process(device, hex_packet)

    expected = {
        Device.main_mode: MainMode.WARM,
        Device.sub_mode: SubMode.NORMAL,
        Device.fan_speed: FanGear.HIGH,
        Device.power_mode: PowerMode.STANDBY,
        Device.power: False,
        Device.target_temperature: 60,
        Device.temp_unit: units.Temperature.F,
        Device.target_temperature_min: 60,
        Device.target_temperature_max: 86,
        Device.ambient_temperature: 63.62,
        Device.outlet_temperature: 61.92,
        Device.wte_fth_en: 2,
        Device.automatic_drain: False,
        Device.drain_mode: DrainMode.EXTERNAL,
        Device.water_level: WaterLevel.LOW,
        Device.ambient_light: False,
        Device.battery_level: 0,
        Device.power_battery: 0,
        Device.power_psdr: 0,
        Device.power_mppt: 0,
    }

    for field_name, expected_value in expected.items():
        actual_value = device.get_value(field_name)
        assert actual_value == expected_value, (
            f"{field_name}: expected {expected_value}, got {actual_value}"
        )


@pytest.mark.parametrize(
    ("packet_name", "expected_unit", "expected_min", "expected_max", "expected_temp"),
    [
        ("heat_celsius_target_16", units.Temperature.C, 16, 30, 16),
        ("heat_celsius_target_30", units.Temperature.C, 16, 30, 30),
        ("fan_fahrenheit_target_60", units.Temperature.F, 60, 86, 60),
        ("heat_fahrenheit_target_86", units.Temperature.F, 60, 86, 86),
    ],
)
async def test_temperature_unit_and_limits_follow_device_temp_sys(
    device, packet_name, expected_unit, expected_min, expected_max, expected_temp
):
    await _process(device, PACKETS[packet_name])

    assert device.temp_unit is expected_unit
    assert device.target_temperature_min == expected_min
    assert device.target_temperature_max == expected_max
    assert device.target_temperature == expected_temp


@pytest.mark.parametrize(
    ("packet_name", "expected_mode"),
    [
        ("fan_celsius_target_30", MainMode.FAN),
        ("heat_celsius_target_30", MainMode.WARM),
    ],
)
async def test_main_mode_is_decoded_from_heartbeat(device, packet_name, expected_mode):
    await _process(device, PACKETS[packet_name])

    assert device.main_mode is expected_mode


@pytest.mark.parametrize(
    ("packet_name", "expected_auto"),
    [
        # in Heat mode only wte_fth_en == 1 means auto drain is active
        ("heat_drain_wte_zero", False),
        ("heat_drain_on", True),
        ("heat_drain_off_external", False),
        ("heat_drain_off_drain_free", False),
    ],
)
async def test_heat_mode_drain_state_is_decoded_from_wte_fth_en(
    device, packet_name, expected_auto
):
    await _process(device, PACKETS[packet_name])

    assert device.automatic_drain is expected_auto
    assert device.drain_mode is DrainMode.EXTERNAL


def test_drain_state_is_unknown_before_first_heartbeat(device):
    assert device.automatic_drain is None
    assert device.drain_mode is None


@pytest.mark.parametrize(
    ("packet_name", "enabled", "expected_payload"),
    [
        # drain-free is unsupported in Heat/Fan; enabling always sends 1 and
        # disabling preserves the drain-mode preference bit
        ("heat_drain_wte_zero", True, 1),
        ("heat_drain_off_external", True, 1),
        ("heat_drain_on", False, 3),
        ("fan_fahrenheit_target_60", True, 1),
    ],
)
async def test_enable_automatic_drain_outside_cool_mode(
    device, packet_name, enabled, expected_payload
):
    await _process(device, PACKETS[packet_name])

    await device.enable_automatic_drain(enabled)

    assert _sent_drain_payload(device) == expected_payload.to_bytes()


# No Cool-mode heartbeats exist in the available captures, so Cool-mode drain
# behavior is exercised by setting the decoded fields directly.
def _force_cool_mode(device: Device, wte_fth_en: int):
    device.main_mode = MainMode.COLD.value
    device.wte_fth_en = wte_fth_en


@pytest.mark.parametrize(
    ("wte_fth_en", "expected_auto", "expected_mode"),
    [
        (0, True, DrainMode.EXTERNAL),
        (1, True, DrainMode.DRAIN_FREE),
        (2, False, DrainMode.EXTERNAL),
        (3, False, DrainMode.DRAIN_FREE),
    ],
)
def test_cool_mode_drain_state_is_decoded_from_wte_fth_en(
    device, wte_fth_en, expected_auto, expected_mode
):
    _force_cool_mode(device, wte_fth_en)

    assert device.automatic_drain is expected_auto
    assert device.drain_mode is expected_mode


@pytest.mark.parametrize(
    ("wte_fth_en", "enabled", "expected_payload"),
    [
        (2, True, 0),
        (3, True, 1),
        (0, False, 2),
        (1, False, 3),
    ],
)
async def test_enable_automatic_drain_in_cool_mode_preserves_preference(
    device, wte_fth_en, enabled, expected_payload
):
    _force_cool_mode(device, wte_fth_en)

    await device.enable_automatic_drain(enabled)

    assert _sent_drain_payload(device) == expected_payload.to_bytes()


@pytest.mark.parametrize(
    ("wte_fth_en", "mode", "expected_payload"),
    [
        (0, DrainMode.DRAIN_FREE, 1),
        (1, DrainMode.EXTERNAL, 0),
        # with auto drain off only the preference bit is stored
        (2, DrainMode.DRAIN_FREE, 3),
        (3, DrainMode.EXTERNAL, 2),
    ],
)
async def test_set_drain_mode_in_cool_mode_sends_new_wte_value(
    device, wte_fth_en, mode, expected_payload
):
    _force_cool_mode(device, wte_fth_en)

    await device.set_drain_mode(mode)

    assert _sent_drain_payload(device) == expected_payload.to_bytes()


@pytest.mark.parametrize("packet_name", ["heat_drain_on", "fan_fahrenheit_target_60"])
@pytest.mark.parametrize("mode", [DrainMode.DRAIN_FREE, DrainMode.EXTERNAL])
async def test_set_drain_mode_is_a_noop_outside_cool_mode(device, packet_name, mode):
    await _process(device, PACKETS[packet_name])
    device._conn.send_packet.reset_mock()

    await device.set_drain_mode(mode)

    device._conn.send_packet.assert_not_called()


def test_power_mode_select_hides_internal_init_state(device):
    select = next(
        c
        for c in device.get_controls(control_type=controls.select)
        if c.key == "power_mode"
    )

    assert select.options_str == ["on", "standby", "off"]

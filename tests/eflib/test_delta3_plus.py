import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.delta3_plus import Device
from custom_components.ef_ble.eflib.packet import Packet


def _station_payload(
    *,
    soc: int = 97,
    voltage_mv: int = 55_895,
    current_ma: int = -278,
    product: int = 79,
    detail: int = 2,
    length: int = 132,
) -> bytes:
    payload = bytearray(length)
    if length > 1:
        payload[1] = 132
    if length > 19:
        payload[19] = product
    if length > 21:
        payload[21] = detail
    if length > 56:
        payload[56] = soc
    if length > 60:
        payload[57:61] = voltage_mv.to_bytes(4, "little")
    if length > 64:
        payload[61:65] = current_ma.to_bytes(4, "little", signed=True)
    return bytes(payload)


def _station_frame(payload: bytes) -> bytes:
    return Packet(0x03, 0x21, 0x03, 0x2F, payload).to_bytes()


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "P351TEST0001")
    device._conn = mocker.AsyncMock()
    return device


@pytest.mark.parametrize(
    ("current_ma", "expected_current"),
    [
        (-278, -0.278),
        (8_273, 8.273),
    ],
    ids=["near_full", "charging"],
)
async def test_station_report_updates_pack_voltage_and_current(
    device, current_ma, expected_current
):
    frame = _station_frame(_station_payload(current_ma=current_ma))
    packet = await device.packet_parse(frame)

    assert packet.src == 0x03
    assert packet.cmd_set == 0x03
    assert packet.cmd_id == 0x2F
    assert await device.data_parse(packet) is True
    assert device.battery_voltage == 55.895
    assert device.battery_current == expected_current
    assert Device.battery_voltage.public_name in device.updated_fields
    assert Device.battery_current.public_name in device.updated_fields


async def test_station_report_ignores_other_product_layout(device):
    packet = await device.packet_parse(
        _station_frame(_station_payload(product=80, current_ma=8_273))
    )

    assert await device.data_parse(packet) is True
    assert device.battery_voltage is None
    assert device.battery_current is None


async def test_station_report_ignores_short_payload(device):
    packet = await device.packet_parse(_station_frame(_station_payload(length=64)))

    assert await device.data_parse(packet) is True
    assert device.battery_voltage is None
    assert device.battery_current is None

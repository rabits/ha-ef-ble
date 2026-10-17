import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices import (
    stream_microinverter,
    stream_microinverter_us,
)
from custom_components.ef_ble.eflib.packet import Packet
from custom_components.ef_ble.eflib.pb import bk_series_pb2


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = stream_microinverter_us.Device(ble_dev, adv_data, "N011XXXXXXXXX388")
    device._conn = mocker.AsyncMock()
    return device


def _display_property_packet(**fields) -> Packet:
    payload = bk_series_pb2.DisplayPropertyUpload(**fields).SerializeToString()
    return Packet(0x02, 0x21, 0xFE, 0x15, payload, 0x01, 0x01, 0x03)


@pytest.mark.parametrize(
    ("serial", "expected"),
    [
        (b"N011XXXXXXXXX388", True),
        (b"BK01XXXXXXXXX001", False),
        (b"BK02XXXXXXXXX001", False),
    ],
)
def test_us_variant_claims_only_its_own_serial_prefix(serial, expected):
    assert stream_microinverter_us.Device.check(serial) is expected


@pytest.mark.parametrize("serial", [b"BK01XXXXXXXXX001", b"BK02XXXXXXXXX001"])
def test_two_input_microinverter_still_claims_the_original_prefixes(serial):
    assert stream_microinverter.Device.check(serial) is True


def test_two_input_microinverter_no_longer_claims_the_us_prefix():
    assert stream_microinverter.Device.check(b"N011XXXXXXXXX388") is False


def test_two_input_microinverter_does_not_gain_the_extra_inputs():
    """The extra inputs must not leak onto a model that only has two of them"""
    for name in ("pv_power_3", "pv_voltage_3", "pv_current_3", "pv_power_4"):
        assert not hasattr(stream_microinverter.Device, name)


async def test_reports_all_four_pv_inputs(device):
    """
    The US variant exposes four inputs

    Values follow a capture where the third and fourth sockets carried the panels: the
    first two read zero while the third and fourth report real power.
    """
    packet = _display_property_packet(
        pow_get_pv=0.0,
        plug_in_info_pv_vol=0.1,
        plug_in_info_pv_amp=0.0,
        pow_get_pv2=0.56,
        plug_in_info_pv2_vol=28.9,
        plug_in_info_pv2_amp=0.02,
        pow_get_pv3=204.56,
        plug_in_info_pv3_vol=28.9,
        plug_in_info_pv3_amp=7.08,
        pow_get_pv4=100.35,
        plug_in_info_pv4_vol=29.1,
        plug_in_info_pv4_amp=3.45,
    )

    assert await device.data_parse(packet)

    assert device.pv_power_1 == 0.0
    assert device.pv_power_2 == 0.56
    assert device.pv_power_3 == 204.56
    assert device.pv_power_4 == 100.35

    assert device.pv_voltage_3 == 28.9
    assert device.pv_current_3 == 7.08
    assert device.pv_voltage_4 == 29.1
    assert device.pv_current_4 == 3.45

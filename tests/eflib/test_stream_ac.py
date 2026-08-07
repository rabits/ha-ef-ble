import pytest

from custom_components.ef_ble.eflib.devices.stream_ac import Device
from custom_components.ef_ble.eflib.packet import Packet
from custom_components.ef_ble.eflib.pb import bk_series_pb2


@pytest.fixture
def device(mocker):
    ble_dev = mocker.Mock(address="AA:BB:CC:DD:EE:FF")
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "BK51TEST1234")
    device._conn = mocker.AsyncMock()
    return device


@pytest.mark.asyncio
async def test_stream_enables_display_property_upload(device):
    await device._enable_property_upload()

    device._conn.sendPacket.assert_awaited_once()
    packet = device._conn.sendPacket.await_args.args[0]

    assert packet == Packet(
        src=0x20,
        dst=0x02,
        cmd_set=0xFE,
        cmd_id=0x11,
        payload=packet.payload,
        dsrc=0x01,
        ddst=0x01,
        version=0x13,
    )

    config = bk_series_pb2.ConfigWrite()
    config.ParseFromString(packet.payload)
    assert config.active_display_property_full_upload is True
    assert config.HasField("cfg_utc_time")


@pytest.mark.asyncio
async def test_stream_processes_display_property_upload(device):
    message = bk_series_pb2.DisplayPropertyUpload(cms_batt_soc=73.5)
    packet = Packet(
        src=0x02,
        dst=0x20,
        cmd_set=0xFE,
        cmd_id=0x15,
        payload=message.SerializeToString(),
    )

    assert await device.data_parse(packet) is True
    assert device.battery_level == 73.5

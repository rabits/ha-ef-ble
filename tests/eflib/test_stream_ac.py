import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices import stream_ac
from custom_components.ef_ble.eflib.exceptions import NotConnectedError
from custom_components.ef_ble.eflib.packet import Packet
from custom_components.ef_ble.eflib.pb import bk_series_pb2

SERIAL = "BK51XXXXXXXXX001"


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    device = stream_ac.Device(ble_dev, mocker.MagicMock(), SERIAL)
    device._conn = mocker.AsyncMock()
    return device


async def test_failed_timer_task_send_raises_the_send_error(device):
    """A failed send reports its own error even after the pending edits were cleared"""
    upload = bk_series_pb2.DisplayPropertyUpload()
    task = upload.all_timer_task.time_task.add()
    task.task_index = 1
    task.chg_task.dev_target_soc.add(sn=SERIAL, target_soc=50)
    await device.data_parse(
        Packet(0x02, 0x21, 0xFE, 0x15, upload.SerializeToString(), 0x01, 0x01, 0x13)
    )

    async def link_drops(*_args, **_kwargs):
        # The clear scheduled by an earlier edit runs while this send is in flight
        device._get_chain().pending_mods.clear()
        raise NotConnectedError

    device._conn.send_packet.side_effect = link_drops

    with pytest.raises(NotConnectedError):
        await device.set_charging_grid_target_soc(80)

import asyncio

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.reconnect import ReconnectManager


@pytest.fixture
def callbacks(mocker: MockerFixture):
    return {
        "fallback": mocker.Mock(),
        "on_success": mocker.Mock(),
        "on_error": mocker.Mock(),
    }


def test_reconnect_manager_preserves_default_reload(callbacks, mocker: MockerFixture):
    device = mocker.Mock(RECONNECT_IN_PLACE=False)
    reconnect = mocker.AsyncMock()
    create_task = mocker.Mock()
    manager = ReconnectManager(
        device,
        reconnect,
        callbacks["fallback"],
        create_task,
    )

    manager.on_disconnect(None)

    callbacks["fallback"].assert_called_once_with()
    create_task.assert_not_called()
    device.set_reconnecting.assert_not_called()


async def test_reconnect_manager_starts_only_one_task(callbacks, mocker: MockerFixture):
    device = mocker.Mock(RECONNECT_IN_PLACE=True)
    release = asyncio.Event()
    reconnect_started = asyncio.Event()

    async def reconnect():
        reconnect_started.set()
        await release.wait()

    manager = ReconnectManager(
        device,
        reconnect,
        callbacks["fallback"],
        asyncio.create_task,
        callbacks["on_success"],
        callbacks["on_error"],
    )

    manager.on_disconnect(None)
    first_task = manager._task
    await reconnect_started.wait()
    manager.on_disconnect(None)

    assert manager._task is first_task
    release.set()
    await first_task
    assert device.set_reconnecting.call_args_list == [
        mocker.call(True),
        mocker.call(False),
    ]
    callbacks["on_success"].assert_called_once_with()
    callbacks["fallback"].assert_not_called()


async def test_reconnect_manager_falls_back_after_failure(
    callbacks, mocker: MockerFixture
):
    device = mocker.Mock(RECONNECT_IN_PLACE=True)
    error = ConnectionError("reconnect failed")
    reconnect = mocker.AsyncMock(side_effect=error)
    manager = ReconnectManager(
        device,
        reconnect,
        callbacks["fallback"],
        asyncio.create_task,
        callbacks["on_success"],
        callbacks["on_error"],
    )

    manager.on_disconnect(None)
    task = manager._task
    await task

    assert device.set_reconnecting.call_args_list == [
        mocker.call(True),
        mocker.call(False),
    ]
    callbacks["on_error"].assert_called_once_with(error)
    callbacks["fallback"].assert_called_once_with()
    callbacks["on_success"].assert_not_called()


async def test_reconnect_manager_cancels_active_task(callbacks, mocker: MockerFixture):
    device = mocker.Mock(RECONNECT_IN_PLACE=True)
    reconnect = mocker.AsyncMock(side_effect=asyncio.Event().wait)
    manager = ReconnectManager(
        device,
        reconnect,
        callbacks["fallback"],
        asyncio.create_task,
    )

    manager.on_disconnect(None)
    task = manager._task
    await asyncio.sleep(0)
    manager.cancel()

    assert device.set_reconnecting.call_args_list == [
        mocker.call(True),
        mocker.call(False),
    ]
    with pytest.raises(asyncio.CancelledError):
        await task
    callbacks["fallback"].assert_not_called()

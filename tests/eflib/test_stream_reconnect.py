from unittest.mock import AsyncMock

import pytest

from custom_components.ef_ble.eflib.connection import Connection, ConnectionState
from custom_components.ef_ble.eflib.devices.stream_ac import Device as StreamAcDevice
from custom_components.ef_ble.eflib.devices.stream_max import Device as StreamMaxDevice


def _connection(mocker, address: str = "AA:BB:CC:DD:EE:01"):
    ble_dev = mocker.Mock(address=address, name="STREAM")
    return Connection(
        ble_dev=ble_dev,
        dev_sn="BK51TEST1234",
        user_id="user",
        data_parse=AsyncMock(),
        packet_parse=AsyncMock(),
    )


def test_stream_uses_native_reconnect():
    assert StreamAcDevice.__new__(StreamAcDevice).uses_native_reconnect is True
    assert StreamMaxDevice.__new__(StreamMaxDevice).uses_native_reconnect is False


def test_reconnect_delay_is_stable_but_separates_devices(mocker):
    first = _connection(mocker, "AA:BB:CC:DD:EE:01")
    second = _connection(mocker, "AA:BB:CC:DD:EE:02")
    options = Connection.Options(
        reconnect_delay=5,
        reconnect_delay_max=60,
        reconnect_jitter=0.25,
    )
    first.with_options(options)
    second.with_options(options)
    first._reconnect_attempt = 1
    second._reconnect_attempt = 1

    assert first._reconnect_delay() != second._reconnect_delay()
    assert 5 <= first._reconnect_delay() <= 6.25
    assert 5 <= second._reconnect_delay() <= 6.25


@pytest.mark.asyncio
async def test_reconnect_retries_failed_rebuild_until_authenticated(mocker):
    connection = _connection(mocker)
    connection.with_options(
        Connection.Options(
            max_connection_attempts=0,
            max_reconnect_attempts=3,
            reconnect_delay=0,
            reconnect_delay_max=0,
        )
    )
    connection._retry_on_disconnect = True
    sleep = mocker.patch(
        "custom_components.ef_ble.eflib.connection.asyncio.sleep",
        new_callable=AsyncMock,
    )
    connect_calls = 0

    async def connect():
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls < 3:
            connection._set_state(
                ConnectionState.ERROR_BLEAK, RuntimeError("temporary BLE error")
            )
        else:
            connection._set_state(ConnectionState.AUTHENTICATED)

    connection.connect = connect

    await connection.reconnect()

    assert connect_calls == 3
    assert sleep.await_count == 3
    assert connection._state is ConnectionState.AUTHENTICATED

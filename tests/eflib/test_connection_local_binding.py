"""Tests for the opt-in local-binding auth path in Connection."""

import hashlib

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.connection import Connection, ConnectionState
from custom_components.ef_ble.eflib.exceptions import AuthErrors
from custom_components.ef_ble.eflib.packet import Packet

USER_ID = "1234567890"
DEV_SN = "R655TEST1234"


@pytest.fixture
def make_connection(mocker: MockerFixture):
    """Factory for a Connection with the BLE-side dependencies stubbed out."""

    def _factory(local_binding: bool = False) -> Connection:
        ble_dev = mocker.Mock()
        ble_dev.address = "AA:BB:CC:DD:EE:FF"

        conn = Connection(
            ble_dev=ble_dev,
            dev_sn=DEV_SN,
            user_id=USER_ID,
            data_parse=mocker.AsyncMock(return_value=False),
            packet_parse=mocker.AsyncMock(),
            local_binding=local_binding,
        )
        mocker.patch.object(conn, "sendPacket", new=mocker.AsyncMock())
        return conn

    return _factory


async def test_set_authentication_sends_md5_payload_as_0x85(make_connection):
    """`_set_authentication` builds a 0x85 packet with hex(MD5(user_id + sn))."""
    conn = make_connection(local_binding=True)

    await conn._set_authentication()

    conn.sendPacket.assert_awaited_once()
    packet: Packet = conn.sendPacket.call_args.args[0]
    assert packet.cmd_set == 0x35
    assert packet.cmd_id == 0x85
    assert packet.src == 0x21
    assert packet.dst == conn._auth_header_dst

    expected = hashlib.md5((USER_ID + DEV_SN).encode("ASCII")).hexdigest().upper()
    assert packet.payload == expected.encode("ASCII")


async def test_handler_sends_bind_on_need_bind_install_first_when_local_binding(
    make_connection, mocker: MockerFixture
):
    """0x86 + payload 0x04 + local_binding=True -> send 0x85, stay AUTHENTICATING."""
    conn = make_connection(local_binding=True)
    conn._connection_state = ConnectionState.AUTHENTICATING

    reply = Packet(
        src=conn._auth_header_dst,
        dst=0x21,
        cmd_set=0x35,
        cmd_id=0x86,
        payload=b"\x04",
    )
    mocker.patch.object(conn, "parseEncPackets", return_value=[reply])
    set_auth_spy = mocker.patch.object(
        conn, "_set_authentication", new=mocker.AsyncMock()
    )

    await conn.listenForDataHandler(mocker.Mock(), bytearray(b"ignored"))

    set_auth_spy.assert_awaited_once()
    assert conn._state == ConnectionState.AUTHENTICATING
    assert not conn._connected.is_set()


async def test_handler_raises_on_need_bind_install_first_when_local_binding_disabled(
    make_connection, mocker: MockerFixture
):
    """Regression guard: with the flag off the existing error path still fires."""
    conn = make_connection(local_binding=False)
    conn._connection_state = ConnectionState.AUTHENTICATING

    reply = Packet(
        src=conn._auth_header_dst,
        dst=0x21,
        cmd_set=0x35,
        cmd_id=0x86,
        payload=b"\x04",
    )
    mocker.patch.object(conn, "parseEncPackets", return_value=[reply])
    set_auth_spy = mocker.patch.object(
        conn, "_set_authentication", new=mocker.AsyncMock()
    )

    with pytest.raises(AuthErrors.NeedBindInstallFirst):
        await conn.listenForDataHandler(mocker.Mock(), bytearray(b"ignored"))

    set_auth_spy.assert_not_awaited()
    assert conn._state == ConnectionState.ERROR_AUTH_FAILED


async def test_handler_transitions_to_authenticated_on_bind_reply(
    make_connection, mocker: MockerFixture
):
    """0x85 success reply during AUTHENTICATING completes the bind."""
    conn = make_connection(local_binding=True)
    conn._connection_state = ConnectionState.AUTHENTICATING

    reply = Packet(
        src=conn._auth_header_dst,
        dst=0x21,
        cmd_set=0x35,
        cmd_id=0x85,
        payload=b"\x00",
    )
    mocker.patch.object(conn, "parseEncPackets", return_value=[reply])

    await conn.listenForDataHandler(mocker.Mock(), bytearray(b"ignored"))

    assert conn._state == ConnectionState.AUTHENTICATED
    assert conn._connected.is_set()

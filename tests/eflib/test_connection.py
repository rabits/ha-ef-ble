"""Hardware-free regression tests for the Bluetooth authentication handshake"""

import asyncio
import ctypes
import hashlib
from collections.abc import Callable

import pytest
from bleak.backends.device import BLEDevice
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib import ecdh
from custom_components.ef_ble.eflib.connection import Connection, ConnectionState
from custom_components.ef_ble.eflib.encryption import Type7Encryption
from custom_components.ef_ble.eflib.frame_assembler import (
    EncPacketAssembler,
    SimplePacketAssembler,
)
from custom_components.ef_ble.eflib.packet import Packet

from .ecdh_vectors import (
    INITIAL_KEY,
    IV,
    KEY_INFO_REPLY,
    PUBLIC_KEYS,
    PUBLIC_REQUEST,
    SESSION_KEY,
)


@pytest.fixture
def connection(mocker: MockerFixture) -> Connection:
    connection = Connection(
        BLEDevice("AA:BB:CC:DD:EE:FF", "Synthetic EcoFlow", {}),
        "Y711TEST000000001",
        "123456789",
        mocker.AsyncMock(return_value=True),
        mocker.AsyncMock(side_effect=Packet.from_bytes),
    ).with_disabled_reconnect()
    connection._client = mocker.Mock(is_connected=True)
    connection._client.write_gatt_char = mocker.AsyncMock()
    connection._client.disconnect = mocker.AsyncMock()
    connection._inbox = asyncio.Queue()
    return connection


@pytest.fixture
def fixed_key(fixed_ecdh_key: Callable[[int], None]) -> None:
    fixed_ecdh_key(130)


@pytest.mark.parametrize("fragmented", [False, True])
@pytest.mark.usefixtures("fixed_key")
async def test_type7_key_exchange(connection: Connection, fragmented: bool) -> None:
    reply = SimplePacketAssembler.encode(b"\x01\x00\x00" + PUBLIC_KEYS[1])
    notifications = [reply[:11], reply[11:]] if fragmented else [reply]
    for notification in notifications:
        await connection._on_notification(None, bytearray(notification))

    await connection._ecdh_key_exchange()

    writes = connection._client.write_gatt_char.call_args_list
    assert len(writes) == 1
    assert bytes(writes[0].args[1]) == PUBLIC_REQUEST
    assert connection._encryption.session_key == INITIAL_KEY
    assert connection._encryption.iv == IV
    assert connection._state == ConnectionState.PUBLIC_KEY_RECEIVED
    assert not connection._stage_reading


@pytest.mark.usefixtures("fixed_key")
async def test_type7_session_key_and_authentication(connection: Connection) -> None:
    peer_reply = SimplePacketAssembler.encode(b"\x01\x00\x00" + PUBLIC_KEYS[1])
    device_assembler = EncPacketAssembler(Type7Encryption(SESSION_KEY, IV))
    auth_reply = await device_assembler.encode(Packet(0x35, 0x21, 0x35, 0x89, b"\x00"))
    # The inbox and frame assemblers must handle stale opcodes, undersized
    # replies, fragments, and duplicate key replies without breaking the handshake.
    notifications = [
        SimplePacketAssembler.encode(b"\x02" + bytes(32)),
        SimplePacketAssembler.encode(b"\x01\x00\x00"),
        peer_reply[:13],
        peer_reply[13:],
        peer_reply,
        KEY_INFO_REPLY[:17],
        KEY_INFO_REPLY[17:],
        peer_reply,
        auth_reply,
    ]
    for notification in notifications:
        await connection._on_notification(None, bytearray(notification))
    derived_keys = []
    connection.on_session_key_derived(lambda key, iv: derived_keys.append((key, iv)))

    await connection._init_ble_session_key()

    assert connection._state == ConnectionState.AUTH_STATUS_RECEIVED
    assert connection._initial_session_key == INITIAL_KEY
    assert derived_keys == [(INITIAL_KEY, IV), (SESSION_KEY, IV)]
    assert connection._errors == 0
    await connection._auto_authentication()

    writes = connection._client.write_gatt_char.call_args_list
    assert len(writes) == 4
    assert bytes(writes[0].args[1]) == PUBLIC_REQUEST
    assert bytes(writes[1].args[1]) == SimplePacketAssembler.encode(b"\x02")
    for write, command in zip(writes[2:], (0x89, 0x86), strict=True):
        frame = bytes(write.args[1])
        plaintext = unpad(
            AES.new(SESSION_KEY, AES.MODE_CBC, IV).decrypt(frame[6:-2]), 16
        )
        packet = Packet.from_bytes(plaintext)
        assert (packet.src, packet.dst, packet.cmd_set, packet.cmd_id) == (
            0x21,
            0x35,
            0x35,
            command,
        )
        assert packet.payload == (
            b"632C5729BDA213663966F2E18019A3BC" if command == 0x86 else b""
        )


@pytest.mark.parametrize("encrypt_type", [0, 1])
async def test_other_modes_do_not_use_ecdh(
    connection: Connection, mocker: MockerFixture, encrypt_type: int
) -> None:
    connection._encrypt_type = encrypt_type
    load_backend = mocker.patch.object(
        ecdh, "_load_libcrypto", side_effect=AssertionError
    )
    mocker.patch.object(connection, "_start_data_pump")
    mocker.patch.object(connection, "_wait_authenticated")

    await connection._run_auth()

    load_backend.assert_not_called()
    if encrypt_type == 0:
        assert connection._encryption is None
    else:
        assert (
            connection._encryption.session_key
            == hashlib.md5(connection._dev_sn.encode()).digest()
        )
        assert (
            connection._encryption.iv
            == hashlib.md5(connection._dev_sn[::-1].encode()).digest()
        )


@pytest.mark.parametrize("teardown", ["cancel", "timeout", "disconnect"])
async def test_ecdh_wait_cleanup(
    connection: Connection,
    mocker: MockerFixture,
    libcrypto: ctypes.CDLL,
    teardown: str,
) -> None:
    free_key = mocker.spy(libcrypto, "EVP_PKEY_free")
    sent = asyncio.Event()
    connection.on_data_send(lambda _: sent.set())
    if teardown == "timeout":
        connection._options.timeout = 0
    task = asyncio.create_task(connection._ecdh_key_exchange())
    connection._auth_task = task
    try:
        async with asyncio.timeout(5):
            await sent.wait()
            if teardown == "timeout":
                with pytest.raises(TimeoutError):
                    await task
            else:
                if teardown == "disconnect":
                    connection.disconnected()
                else:
                    task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    free_key.assert_called_once()
    assert connection._encryption is None
    assert not connection._stage_reading


@pytest.mark.parametrize("curve_number", [0, 1, 2])
async def test_bad_peer_aborts_authentication(
    connection: Connection,
    mocker: MockerFixture,
    libcrypto: ctypes.CDLL,
    curve_number: int,
) -> None:
    free_key = mocker.spy(libcrypto, "EVP_PKEY_free")
    reply = SimplePacketAssembler.encode(bytes([1, 0, curve_number]) + bytes(40))
    await connection._on_notification(None, bytearray(reply))

    await connection._run_auth()

    assert connection._state == ConnectionState.ERROR_AUTH_FAILED
    assert connection._encryption is None
    connection._client.disconnect.assert_awaited_once()
    free_key.assert_called_once()


async def test_repeated_handshakes_generate_fresh_keys(connection: Connection) -> None:
    reply = SimplePacketAssembler.encode(b"\x01\x00\x00" + PUBLIC_KEYS[1])
    for _ in range(2):
        await connection._on_notification(None, bytearray(reply))
        await connection._ecdh_key_exchange()
    writes = connection._client.write_gatt_char.call_args_list
    assert bytes(writes[0].args[1]) != bytes(writes[1].args[1])

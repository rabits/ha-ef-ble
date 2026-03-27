import asyncio
import contextlib
import functools
import hashlib
import logging
import struct
import time
import traceback
from collections import deque
from collections.abc import Awaitable, Callable, Collection, Coroutine, MutableSequence
from dataclasses import dataclass
from enum import StrEnum, auto
from functools import cached_property
from typing import Literal

import ecdsa
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    MAX_CONNECT_ATTEMPTS,
    BleakNotFoundError,
    establish_connection,
)

from . import keydata
from .encryption import EncryptionStrategy, Type1Encryption, Type7Encryption
from .exceptions import (
    AuthErrors,
    ConnectionTimeout,
    FailedToAuthenticate,
    MaxConnectionAttemptsReached,
    MaxReconnectAttemptsReached,
    PacketParseError,
    PacketReceiveError,
    UnsupportedBluetoothProtocol,
)
from .frame_assembler import (
    EncPacketAssembler,
    RawHeaderAssembler,
    SimplePacketAssembler,
)
from .listeners import ListenerGroup, ListenerRegistry
from .logging_util import ConnectionLogger, LogOptions
from .packet import Packet
from .props.utils import classproperty

MAX_RECONNECT_ATTEMPTS = 2
MAX_CONNECTION_ATTEMPTS = 10


_BT_PROTOCOL_UUIDS = {
    "rfcomm": {
        "notify": "00000003-0000-1000-8000-00805f9b34fb",
        "write": "00000002-0000-1000-8000-00805f9b34fb",
    },
    "nordic_uart": {
        "notify": "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
        "write": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    },
}


def _state_in(states: "Collection[ConnectionState | str]"):
    return cached_property(lambda self: self in states)


def _combine_state(
    prop: cached_property[bool], states: "Collection[ConnectionState | str]"
):
    return cached_property(lambda self: prop.__get__(self) or self in states)


class ConnectionState(StrEnum):
    NOT_CONNECTED = auto()

    CREATED = auto()
    ESTABLISHING_CONNECTION = auto()
    CONNECTED = auto()
    PUBLIC_KEY_EXCHANGE = auto()
    PUBLIC_KEY_RECEIVED = auto()
    REQUESTING_SESSION_KEY = auto()
    SESSION_KEY_RECEIVED = auto()
    REQUESTING_AUTH_STATUS = auto()
    AUTH_STATUS_RECEIVED = auto()
    AUTHENTICATING = auto()
    AUTHENTICATED = auto()

    ERROR_TIMEOUT = auto()
    ERROR_NOT_FOUND = auto()
    ERROR_BLEAK = auto()
    ERROR_PACKET_PARSE = auto()
    ERROR_SEND_REQUEST = auto()
    ERROR_UNKNOWN = auto()
    ERROR_AUTH_FAILED = auto()
    ERROR_TOO_MANY_ERRORS = auto()

    RECONNECTING = auto()
    ERROR_MAX_RECONNECT_ATTEMPTS_REACHED = auto()

    DISCONNECTING = auto()
    DISCONNECTED = auto()

    # helper state descriptor flags
    connection_error = _state_in(
        [
            ERROR_TIMEOUT,
            ERROR_NOT_FOUND,
            ERROR_BLEAK,
        ]
    )

    is_error = _combine_state(
        connection_error,
        [
            ERROR_MAX_RECONNECT_ATTEMPTS_REACHED,
            ERROR_AUTH_FAILED,
            ERROR_TOO_MANY_ERRORS,
            ERROR_UNKNOWN,
        ],
    )
    received_session_key = _state_in(
        [
            SESSION_KEY_RECEIVED,
            REQUESTING_AUTH_STATUS,
            AUTH_STATUS_RECEIVED,
            AUTHENTICATING,
            AUTHENTICATED,
        ]
    )

    is_connected = _state_in(
        [
            CONNECTED,
            PUBLIC_KEY_EXCHANGE,
            PUBLIC_KEY_RECEIVED,
            SESSION_KEY_RECEIVED,
            REQUESTING_AUTH_STATUS,
            AUTH_STATUS_RECEIVED,
            AUTHENTICATING,
        ]
    )

    is_connecting = _combine_state(
        is_connected,
        [ESTABLISHING_CONNECTION, RECONNECTING],
    )
    authenticated = _state_in([AUTHENTICATED])
    is_terminal = _combine_state(
        is_error,
        [
            AUTHENTICATED,
            DISCONNECTED,
            NOT_CONNECTED,
        ],
    )

    @classproperty
    @functools.cache
    def step_order(self):
        return [
            ConnectionState.CONNECTED,
            ConnectionState.PUBLIC_KEY_EXCHANGE,
            ConnectionState.PUBLIC_KEY_RECEIVED,
            ConnectionState.REQUESTING_SESSION_KEY,
            ConnectionState.SESSION_KEY_RECEIVED,
            ConnectionState.REQUESTING_AUTH_STATUS,
            ConnectionState.AUTH_STATUS_RECEIVED,
            ConnectionState.AUTHENTICATING,
            ConnectionState.AUTHENTICATED,
        ]

    @cached_property
    def step_index(self):
        if self in self.step_order:
            return self.step_order.index(self)
        return None


type DisconnectListener = Callable[[Exception | type[Exception] | None], None]
type ConnectionStateListener = Callable[[ConnectionState], None]
type PacketReceivedListener = Callable[[bytes], None]
type PacketParsedListener = Callable[[Packet], None]
type DataReceivedListener = Callable[[bytes, ConnectionState], None]
type DataSendListener = Callable[[bytes], None]


class _ConnectionListeners(ListenerRegistry):
    on_packet_received: ListenerGroup[PacketReceivedListener]
    on_disconnect: ListenerGroup[DisconnectListener]
    on_connection_state_change: ListenerGroup[ConnectionStateListener]
    on_packet_parsed: ListenerGroup[PacketParsedListener]
    on_data_received: ListenerGroup[DataReceivedListener]
    on_data_send: ListenerGroup[DataSendListener]


class Connection:
    """Manages client creation, authentification and sends the packets to parse back"""

    @dataclass
    class Options:
        """Connection options configurable from HA."""

        timeout: int = 20
        bluez_start_notify: bool = False

    _listeners = _ConnectionListeners.create()

    def __init__(
        self,
        ble_dev: BLEDevice,
        dev_sn: str,
        user_id: str,
        data_parse: Callable[[Packet], Awaitable[bool]],
        packet_parse: Callable[[bytes], Awaitable[Packet]],
        packet_version: int = 0x03,
        encrypt_type: int = 7,
        auth_header_dst: int = 0x35,
    ) -> None:
        self._ble_dev = ble_dev
        self._address = ble_dev.address
        self._dev_sn = dev_sn
        self._user_id = user_id

        self._data_parse = data_parse
        self._packet_parse = packet_parse
        self._packet_version = packet_version
        self._encrypt_type = encrypt_type
        self._encryption: EncryptionStrategy | None = None
        self._simple_assembler = SimplePacketAssembler()
        self._options = Connection.Options()

        self._errors = 0
        self._last_errors = deque(maxlen=10)
        self._client = None
        self._connected = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._retry_on_disconnect = False
        self._retry_on_disconnect_delay = 10
        self._auth_header_dst = auth_header_dst

        self._tasks: set[asyncio.Task] = set()

        self._logger = ConnectionLogger(self)
        self._state_changed = asyncio.Event()

        self._state_exception: Exception | type[Exception] | None = None
        self._last_exception: Exception | type[Exception] | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._connection_attempt: int = 0
        self._reconnect_attempt: int = 0
        self._reconnect = True

        self._connection_state: ConnectionState = None  # pyright: ignore[reportAttributeAccessIssue]
        self._set_state(ConnectionState.CREATED)

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @cached_property
    def mtu_size(self):
        return self._client.mtu_size

    def _add_listener(self, collection: MutableSequence[Callable], listener: Callable):
        collection.append(listener)

        def _unlisten():
            collection.remove(value=listener)

        return _unlisten

    def on_disconnect(self, listener: DisconnectListener):
        """
        Add disconnect listener

        Parameters
        ----------
        listener
            Listener that will be called on disconnect that receives exception as a
            param if one occured before device disconnected

        Return
        -------
        Function to remove this listener
        """
        return self._listeners.on_disconnect.add(listener)

    def on_state_change(self, listener: ConnectionStateListener):
        return self._listeners.on_connection_state_change.add(listener)

    def on_packet_data_received(self, listener: PacketReceivedListener):
        return self._listeners.on_packet_received.add(listener)

    def on_packet_parsed(self, listener: PacketParsedListener):
        return self._listeners.on_packet_parsed.add(listener)

    def on_data_received(self, listener: DataReceivedListener):
        return self._listeners.on_data_received.add(listener)

    def on_data_send(self, listener: DataSendListener):
        return self._listeners.on_data_send.add(listener)

    def _notify_disconnect(self, exception: Exception | type[Exception] | None = None):
        if exception is None:
            exception = self._last_exception

        self._listeners.on_disconnect(exception)

    def ble_dev(self) -> BLEDevice:
        return self._ble_dev

    def with_logging_options(self, options: LogOptions):
        self._logger.set_options(options)
        return self

    def with_disabled_reconnect(self, is_disabled: bool = True):
        self._reconnect = not is_disabled
        return self

    def with_options(self, options: "Connection.Options"):
        """Set connection options."""
        self._options = options
        return self

    async def connect(
        self,
        max_attempts: int | None = None,
    ):
        if self._state.is_connecting:
            return

        max_attempts = (
            max_attempts if max_attempts is not None else MAX_CONNECT_ATTEMPTS
        )

        self._connection_attempt += 1
        if max_attempts != 0 and self._connection_attempt > max_attempts:
            self._connection_attempt = 0
            err = MaxConnectionAttemptsReached(
                last_error=self._last_exception,
                attempts=MAX_CONNECTION_ATTEMPTS,
            )
            self._set_state(ConnectionState.ERROR_MAX_RECONNECT_ATTEMPTS_REACHED, err)
            self._notify_disconnect(self._last_exception)
            raise err

        self._connected.clear()
        self._disconnected.clear()

        error = None
        try:
            if self.is_connected:
                self._logger.warning("Device is already connected")
                return

            self._set_state(ConnectionState.ESTABLISHING_CONNECTION)
            self._logger.info("Connecting to device")
            # max_attempts=0 means unlimited at Connection level, but
            # establish_connection needs a real retry count for BLE-level
            # attempts (e.g. when adapter slots are contested).
            ble_attempts = max_attempts if max_attempts != 0 else MAX_CONNECT_ATTEMPTS
            self._client = await establish_connection(
                BleakClient,
                self.ble_dev(),
                self._ble_dev.name,
                disconnected_callback=self.disconnected,
                ble_device_callback=self.ble_dev,
                max_attempts=ble_attempts,
                timeout=self._options.timeout,
            )
        except TimeoutError as e:
            error = e
            self._set_state(
                ConnectionState.ERROR_TIMEOUT,
                ConnectionTimeout().with_traceback(e.__traceback__),
            )
        except BleakNotFoundError as e:
            error = e
            self._set_state(ConnectionState.ERROR_NOT_FOUND, e)
        except BleakError as e:
            error = e
            self._set_state(ConnectionState.ERROR_BLEAK, e)

        if error is not None:
            if self._client is not None and self._client.is_connected:
                await self._client.disconnect()

            self._logger.error("Failed to connect to the device: %s", error)
            self._last_errors.append(f"Failed to connect to the device: {error}")
            self.disconnected()
            return

        self._set_state(ConnectionState.CONNECTED)
        self._logger.info("Connected")
        self._errors = 0
        self._retry_on_disconnect = self._reconnect

        if self._client._backend.__class__.__name__ == "BleakClientBlueZDBus":
            await self._client._backend._acquire_mtu()

        self._logger.log_filtered(LogOptions.CONNECTION_DEBUG, "MTU: %d", self.mtu_size)
        self._logger.info("Init completed, starting auth routine...")

        await self.initBleSessionKey()

    def disconnected(self, *args, **kwargs) -> None:
        self._logger.warning("Disconnected from device")
        self._client = None

        if not self._retry_on_disconnect:
            if self._reconnect_task:
                self._reconnect_task.cancel()

            self._connected.set()
            self._disconnected.set()
            if self._state is not ConnectionState.DISCONNECTING:
                self._notify_disconnect()
            self._set_state(ConnectionState.DISCONNECTED)
            return

        if self._reconnect_task is not None:
            return

        loop = asyncio.get_event_loop()
        self._reconnect_task = self._add_task(self.reconnect(), loop)

        def _reconnect_done(task: asyncio.Task[None]):
            self._reconnect_task = None
            with contextlib.suppress(asyncio.CancelledError):
                if exc := task.exception():
                    raise exc

        self._reconnect_task.add_done_callback(_reconnect_done)

    async def reconnect(self) -> None:
        # Wait before reconnect
        if self._reconnect_attempt == 0:
            self._retry_on_disconnect_delay = 10

        self._reconnect_attempt += 1
        if self._reconnect_attempt > MAX_RECONNECT_ATTEMPTS:
            self._logger.error(
                "Could not reconnect after %d attempts", MAX_RECONNECT_ATTEMPTS
            )
            self._set_state(
                ConnectionState.ERROR_MAX_RECONNECT_ATTEMPTS_REACHED,
                MaxReconnectAttemptsReached(
                    attempts=MAX_RECONNECT_ATTEMPTS,
                    last_error=self._last_exception,
                ),
            )
            self._notify_disconnect(self._last_exception)

            self._reconnect_attempt = 0
            return

        self._logger.warning(
            "Reconnecting to the device in %d seconds, attempt: %d/%d...",
            self._retry_on_disconnect_delay,
            self._reconnect_attempt,
            MAX_RECONNECT_ATTEMPTS,
        )
        await asyncio.sleep(self._retry_on_disconnect_delay)
        if not self._retry_on_disconnect:
            self._logger.warning("Reconnect is aborted")
            return

        self._retry_on_disconnect_delay += 10
        self._set_state(ConnectionState.RECONNECTING)
        await self.connect()

    async def disconnect(self) -> None:
        self._logger.info(msg="Disconnecting from device")
        self._retry_on_disconnect = False

        self._reconnect_attempt = 0
        self._cancel_tasks()

        if self._client is not None and self._client.is_connected:
            self._set_state(ConnectionState.DISCONNECTING)
            await self._client.disconnect()

        self._client = None
        if self._state == ConnectionState.DISCONNECTING:
            self._set_state(ConnectionState.DISCONNECTED)

    async def wait_connected(self, timeout: int = 20):
        """Will release when connection is happened and authenticated"""
        last_state = self._state
        if self.is_connected:
            return

        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
        except TimeoutError as e:
            last_state = self._state
            self._set_state(ConnectionState.ERROR_TIMEOUT, e)

        if self._state is not ConnectionState.AUTHENTICATED:
            self._set_state(
                self._state,
                FailedToAuthenticate(
                    f"Could not connect to device, state: {last_state}"
                ),
            )

    async def wait_until_authenticated_or_error(
        self, raise_on_error: bool = False, return_exc: bool = False
    ):
        while not self._state.is_terminal:
            await self._state_changed.wait()

            if (
                self._state is ConnectionState.ERROR_MAX_RECONNECT_ATTEMPTS_REACHED
                and raise_on_error
            ):
                assert isinstance(self._state_exception, MaxReconnectAttemptsReached)
                raise (
                    self._state_exception.last_error
                    if self._state_exception.last_error is not None
                    else self._state_exception
                )

        if self._state_exception is not None and raise_on_error:
            raise self._state_exception

        if self._state is ConnectionState.DISCONNECTED:
            if return_exc:
                return self._last_state, self._state_exception
            return self._last_state

        if return_exc:
            return self._state, self._state_exception
        return self._state

    async def observe_connection(self):
        while True:
            yield self._state
            await self._state_changed.wait()

    async def wait_disconnected(self):
        """Will release when client got disconnected from the device"""
        if not self.is_connected:
            return

        await self._disconnected.wait()

    async def add_error(self, exception: Exception):
        tb = traceback.format_tb(exception.__traceback__)
        self._logger.error("Captured exception: %s:\n%s", exception, "".join(tb))
        self._errors += 1
        self._last_exception = exception
        if self._errors > 5:
            # Too much errors happened - let's reconnect
            self._errors = 0
            self._set_state(ConnectionState.ERROR_TOO_MANY_ERRORS, exception)
            if self._client is not None and self._client.is_connected:
                self._logger.warning("Client disconnected after encountering 5 errors")
                await self._client.disconnect()

    def _reset_error_counter(self):
        self._errors = 0

    @property
    def _state(self) -> ConnectionState:
        return self._connection_state

    @_state.setter
    def _state(self, value: ConnectionState):
        self._last_state = self._connection_state
        self._connection_state = value
        self._state_changed.set()
        self._state_changed.clear()
        self._listeners.on_connection_state_change(value)

    def _set_state(
        self, state: ConnectionState, exc: Exception | type[Exception] | None = None
    ):
        self._state_exception = exc
        if exc is not None:
            self._last_exception = exc

        self._state = state

        if state.is_error:
            self._notify_disconnect(exc)

    def _get_characteristics(self, char_type: Literal["write", "notify"]):
        assert self._client is not None

        for uuids in _BT_PROTOCOL_UUIDS.values():
            if (
                uuid := self._client.services.get_characteristic(uuids[char_type])
            ) is not None:
                return uuid
        characteristic_list = [
            f"{c.uuid} {c.description} {c.properties}"
            for c in self._client.services.characteristics.values()
        ]
        raise UnsupportedBluetoothProtocol("write", characteristic_list)

    @cached_property
    def _notify_characteristic(self):
        return self._get_characteristics("notify")

    @cached_property
    def _write_characteristic(self):
        return self._get_characteristics("write")

    async def genSessionKey(self, seed: bytes, srand: bytes):
        """Implements the necessary part of the logic, rest is skipped"""
        data_num = [0, 0, 0, 0]

        # Using seed and predefined key to get first 2 numbers
        pos = seed[0] * 0x10 + ((seed[1] - 1) & 0xFF) * 0x100
        data_num[0] = struct.unpack("<Q", keydata.get8bytes(pos))[0]
        pos += 8
        data_num[1] = struct.unpack("<Q", keydata.get8bytes(pos))[0]

        # Getting the last 2 numbers from srand
        srand_len = len(srand)
        # lower_srand_len = srand_len & 0xFFFFFFFF
        if srand_len < 0x20:
            srand_len = 0
        else:
            raise NotImplementedError

        # Just putting srand in there byte-by-byte
        data_num[2] = struct.unpack("<Q", srand[0:8])[0]
        data_num[3] = struct.unpack("<Q", srand[8:16])[0]

        # Converting data numbers to 32 bytes
        data = b""
        data += struct.pack("<Q", data_num[0])
        data += struct.pack("<Q", data_num[1])
        data += struct.pack("<Q", data_num[2])
        data += struct.pack("<Q", data_num[3])

        # Hashing data to get the session key
        return hashlib.md5(data).digest()

    async def parseSimple(self, data: bytes) -> bytes | None:
        """Deserializes bytes stream into the simple bytes"""
        self._listeners.on_data_received(data, self._connection_state)

        self._logger.log_filtered(
            LogOptions.ENCRYPTED_PAYLOADS,
            "parseSimple: Data: %r",
            data,
        )

        try:
            return self._simple_assembler.parse(data)
        except PacketParseError as e:
            error_msg = "parseSimple: Unable to parse simple packet: %r"
            self._logger.error(error_msg, str(e))
            self._last_errors.append(error_msg % str(e))
            raise

    async def parseEncPackets(self, data: bytes) -> list[Packet]:
        """Deserializes bytes stream into a list of Packets"""
        self._listeners.on_data_received(data, self._connection_state)

        self._logger.log_filtered(
            LogOptions.ENCRYPTED_PAYLOADS,
            "parseEncPackets: Data: %r",
            data,
        )

        frame_assembler = (
            self._frame_assembler
            if self._connection_state.received_session_key
            else self._create_frame_assembler()
        )

        decoded_payloads = await frame_assembler.reassemble(data)

        packets = []
        for payload in decoded_payloads:
            try:
                self._listeners.on_packet_received(payload)
                packet = await self._packet_parse(payload)
                self._listeners.on_packet_parsed(packet)

                self._logger.log_filtered(
                    LogOptions.DECRYPTED_PAYLOADS,
                    "decrypted payload: '%s'",
                    payload,
                )

                self._logger.log_filtered(
                    LogOptions.PACKETS,
                    "Parsed packet: %s",
                    packet,
                )
                if not Packet.is_invalid(packet):
                    packets.append(packet)
            except Exception as e:  # noqa: BLE001
                await self.add_error(e)

        return packets

    async def sendRequest(self, send_data: bytes, response_handler=None):
        self._logger.log_filtered(LogOptions.CONNECTION_DEBUG, "Sending: %r", send_data)
        self._listeners.on_data_send(send_data)

        # In case exception happens we need to try again
        err = None
        for retry in range(4):
            try:
                await self._sendRequest(send_data, response_handler)
            except Exception as e:  # noqa: BLE001
                self._logger.log_filtered(
                    LogOptions.CONNECTION_DEBUG,
                    (
                        "Exception occured when sending request on try %d: %s, "
                        "retrying in %d seconds"
                    ),
                    retry,
                    str(e),
                    retry + 1,
                    level=logging.WARNING,
                )
                if err is None:
                    err = e
                await asyncio.sleep(retry + 1)
                continue
            else:
                return

        await self.add_error(err)

    async def _start_notify(self, callback: Callable):
        kwargs = {}
        if self._options.bluez_start_notify:
            kwargs["bluez"] = {"use_start_notify": True}
        await self._client.start_notify(self._notify_characteristic, callback, **kwargs)

    async def _sendRequest(self, send_data: bytes, response_handler=None):
        # Make sure the connection is here, otherwise just skipping
        if self._client is None or not self._client.is_connected:
            self._logger.log_filtered(
                LogOptions.CONNECTION_DEBUG,
                "Skip sending: disconnected: %r",
                send_data,
            )
            return

        if response_handler:
            await self._start_notify(response_handler)

        await self._client.write_gatt_char(
            self._write_characteristic, bytearray(send_data)
        )

    async def sendPacket(
        self, packet: Packet, response_handler=None, wait_for_response: bool = True
    ):
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "Sending packet: %r", packet
        )

        frame_assembler = (
            self._frame_assembler
            if self._connection_state.received_session_key
            else self._create_frame_assembler()
        )

        to_send = await frame_assembler.encode(packet)

        if frame_assembler.write_with_response and wait_for_response:
            await self.sendRequest(to_send, response_handler)
        elif self._client is not None and self._client.is_connected:
            await self._client.write_gatt_char(
                self._write_characteristic, bytearray(to_send), response=False
            )

    async def replyPacket(self, packet: Packet):
        """Copy and change the packet to be reply packet and sends it back to device"""
        # Found it's necesary to send back the packets, otherwise device will not send
        # moar info then strict minimum - which just about power params, but not configs
        # & advanced params
        reply_packet = Packet(
            packet.dst,  # Switching src to dst
            packet.src,  # Switching dst to src
            packet.cmdSet,
            packet.cmdId,
            packet.payload,
            0x01,
            0x01,  # Replacing 0 with 1
            packet.version,
            packet.seq,
            packet.productId,
        )
        # Running reply asynchroneously
        self._add_task(self.sendPacket(reply_packet))

    async def initBleSessionKey(self):
        if self._encrypt_type == 1:
            await self._type_1_session()
        else:
            await self._ecdh_key_exchange()

    async def _type_1_session(self):
        session_key = hashlib.md5(self._dev_sn.encode()).digest()
        iv = hashlib.md5(self._dev_sn[::-1].encode()).digest()
        self._encryption = Type1Encryption(session_key, iv)

        await self._start_notify(self.listenForDataHandler)

        await self.send_auth_status_packet()
        await self.autoAuthentication()

    async def _ecdh_key_exchange(self):
        self._set_state(ConnectionState.PUBLIC_KEY_EXCHANGE)
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "initBleSessionKey: Pub key exchange"
        )
        self._private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP160r1)
        self._public_key: ecdsa.VerifyingKey = self._private_key.get_verifying_key()  # pyright: ignore[reportAttributeAccessIssue]

        to_send = SimplePacketAssembler.encode(
            # Payload contains some weird prefix and generated public key
            b"\x01\x00" + self._public_key.to_string(),
        )

        # Device public key is sent as response, process will continue on device
        # response in handler
        await self.sendRequest(to_send, self.initBleSessionKeyHandler)

    async def initBleSessionKeyHandler(
        self, characteristic: BleakGATTCharacteristic, recv_data: bytearray
    ):
        if self._client is None or not self._client.is_connected:
            return

        data = await self.parseSimple(bytes(recv_data))
        if data is None:
            return

        self._set_state(ConnectionState.PUBLIC_KEY_RECEIVED)
        await self._client.stop_notify(self._notify_characteristic)

        if len(data) < 3:
            raise PacketParseError(
                "Incorrect size of the returned pub key data: " + data.hex()
            )
        # status = data[1]
        ecdh_type_size = getEcdhTypeSize(data[2])
        self._dev_pub_key = ecdsa.VerifyingKey.from_string(
            data[3 : ecdh_type_size + 3], curve=ecdsa.SECP160r1
        )

        # Generating shared key from our private key and received device public key
        # NOTE: The device will do the same with it's private key and our public key to
        # generate the # same shared key value and use it to encrypt/decrypt using
        # symmetric encryption algorithm
        shared_key = ecdsa.ECDH(
            ecdsa.SECP160r1, self._private_key, self._dev_pub_key
        ).generate_sharedsecret_bytes()
        # Set Initialization Vector from digest of the original shared key
        iv = hashlib.md5(shared_key).digest()

        self._encryption = Type7Encryption(shared_key[:16], iv)

        await self.getKeyInfoReq()

    async def getKeyInfoReq(self):
        self._set_state(ConnectionState.REQUESTING_SESSION_KEY)
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "getKeyInfoReq: Receiving session key"
        )
        to_send = SimplePacketAssembler.encode(
            b"\x02",  # command to get key info to make the shared key
        )

        await self.sendRequest(to_send, self.getKeyInfoReqHandler)

    async def getKeyInfoReqHandler(
        self, characteristic: BleakGATTCharacteristic, recv_data: bytearray
    ):
        if self._client is None or not self._client.is_connected:
            return

        encrypted_data = await self.parseSimple(bytes(recv_data))
        if encrypted_data is None:
            return

        self._set_state(ConnectionState.SESSION_KEY_RECEIVED)
        await self._client.stop_notify(self._notify_characteristic)

        if encrypted_data[0] != 0x02:
            exc = AuthErrors.KeyInfoReqFailed(
                "Received type of KeyInfo is != 0x02, need to dig into: "
                f"{encrypted_data.hex()}"
            )
            self._set_state(ConnectionState.ERROR_AUTH_FAILED, exc)
            if self._client is not None and self._client.is_connected:
                await self._client.disconnect()
            raise exc

        assert self._encryption is not None

        # Skipping the first byte - type of the payload (0x02)
        data = await self._encryption.decrypt(encrypted_data[1:])

        # Parse the data that contains sRand (first 16 bytes) & seed (last 2 bytes)
        session_key = await self.genSessionKey(data[16:18], data[:16])
        self._encryption = Type7Encryption(session_key, self._encryption.iv)

        await self.getAuthStatus()

    async def getAuthStatus(self):
        self._set_state(ConnectionState.REQUESTING_AUTH_STATUS)
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "getKeyInfoReq: Receiving auth status"
        )

        packet = Packet(
            0x21,
            self._auth_header_dst,
            0x35,
            0x89,
            b"",
            0x01,
            0x01,
            self._packet_version,
        )

        await self.sendPacket(packet=packet, response_handler=self.getAuthStatusHandler)

    async def getAuthStatusHandler(
        self, characteristic: BleakGATTCharacteristic, recv_data: bytearray
    ):
        if self._client is None or not self._client.is_connected:
            return

        self._set_state(ConnectionState.AUTH_STATUS_RECEIVED)
        await self._client.stop_notify(self._notify_characteristic)
        packets = await self.parseEncPackets(bytes(recv_data))
        if len(packets) < 1:
            raise PacketReceiveError
        data = packets[0].payload

        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG,
            "getAuthStatusHandler: data: %r",
            data,
        )
        await self.autoAuthentication()

    async def autoAuthentication(self):
        self._set_state(ConnectionState.AUTHENTICATING)
        self._logger.info(
            "autoAuthentication: Sending secretKey consists of user id and device "
            "serial number",
        )

        # Building payload for auth
        md5_data = hashlib.md5((self._user_id + self._dev_sn).encode("ASCII")).digest()
        # We need upper case in MD5 data here
        payload = ("".join(f"{c:02X}" for c in md5_data)).encode("ASCII")

        # Forming packet - use detected protocol version (V2 or V3)
        packet = Packet(
            0x21,
            self._auth_header_dst,
            0x35,
            0x86,
            payload,
            0x01,
            0x01,
            self._packet_version,
        )

        # Sending request and starting the common listener
        await self.sendPacket(packet, self.listenForDataHandler)

    async def _check_auth(self, packet: Packet):
        exc = AuthErrors.from_payload(packet.payload)
        if not exc:
            return
        exc = exc(f"Authentication failed with response: {packet.payload.hex()}")

        self._logger.error("Authentication failed, packet: %s", packet, exc_info=exc)
        self._set_state(ConnectionState.ERROR_AUTH_FAILED, exc)

        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()
        raise exc

    async def send_auth_status_packet(self):
        """Send the auth status packet used for initial auth wake-up."""
        pkt = Packet(
            0x21,
            self._auth_header_dst,
            0x35,
            0x89,
            b"",
            0x01,
            0x01,
            self._packet_version,
        )
        await self.sendPacket(pkt)

    async def listenForDataHandler(
        self, characteristic: BleakGATTCharacteristic, recv_data: bytearray
    ):
        try:
            packets = await self.parseEncPackets(bytes(recv_data))
        except Exception as e:  # noqa: BLE001
            await self.add_error(e)
            return

        self._reset_error_counter()

        for packet in packets:
            processed = False

            # Handling autoAuthentication response
            if (
                packet.src == self._auth_header_dst
                and packet.cmdSet == 0x35
                and packet.cmdId == 0x86
            ):
                await self._check_auth(packet)
                self._connection_attempt = 0
                self._reconnect_attempt = 0
                processed = True
                self._logger.info("Auth completed, everything is fine")
                self._set_state(ConnectionState.AUTHENTICATED)
                self._connected.set()
            else:
                try:
                    # Processing the packet with specific device
                    processed = await self._data_parse(packet)
                except Exception as e:  # noqa: BLE001
                    await self.add_error(e)
                    continue

            if not processed:
                self._logger.log_filtered(
                    LogOptions.CONNECTION_DEBUG, "listenForDataHandler: %r", packet
                )

    def _create_frame_assembler(self):
        match self._encrypt_type:
            case 1:
                return RawHeaderAssembler(self._encryption)
            case 7:
                return EncPacketAssembler(self._encryption)
            case _:
                raise ValueError(f"Unsupported encryption type: {self._encrypt_type}")

    @cached_property
    def _frame_assembler(self):
        return self._create_frame_assembler()

    def _cancel_tasks(self):
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    def _add_task(
        self,
        coro: Coroutine,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ):
        task = event_loop.create_task(coro) if event_loop else asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def add_timer_task(
        self,
        coro: Callable[[], Coroutine],
        interval: float = 30,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ):
        async def _timer_task():
            while True:
                start_time = time.monotonic()
                if self._connection_state != ConnectionState.AUTHENTICATED:
                    await self._state_changed.wait()
                    continue
                await coro()

                elapsed = time.monotonic() - start_time
                sleep_time = max(0, interval - (elapsed % interval))
                await asyncio.sleep(sleep_time)

        return self._add_task(_timer_task(), event_loop)


def getEcdhTypeSize(curve_num: int):
    """Return size of ecdh based on type"""
    match curve_num:
        case 1:
            return 52
        case 2:
            return 56
        case 3, 4:
            return 64
        case _:
            return 40

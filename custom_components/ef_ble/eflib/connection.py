import asyncio
import contextlib
import hashlib
import logging
import struct
import traceback
from collections.abc import Awaitable, Callable, Coroutine
from enum import StrEnum, auto

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
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from . import keydata
from .crc import crc16
from .encpacket import EncPacket
from .exceptions import (
    AuthFailedError,
    ConnectionTimeout,
    EncPacketParseError,
    FailedToAuthenticate,
    MaxConnectionAttemptsReached,
    MaxReconnectAttemptsReached,
    PacketParseError,
    PacketReceiveError,
)
from .logging_util import ConnectionLogger, LogOptions
from .packet import Packet

MAX_RECONNECT_ATTEMPTS = 2
MAX_CONNECTION_ATTEMPTS = 10

type DisconnectListener = Callable[[Exception | type[Exception] | None], None]


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

    def connection_error(self):
        return self in [
            ConnectionState.ERROR_TIMEOUT,
            ConnectionState.ERROR_NOT_FOUND,
            ConnectionState.ERROR_BLEAK,
        ]

    def is_connecting(self):
        return self in [
            ConnectionState.ESTABLISHING_CONNECTION,
            ConnectionState.CONNECTED,
            ConnectionState.PUBLIC_KEY_EXCHANGE,
            ConnectionState.PUBLIC_KEY_RECEIVED,
            ConnectionState.SESSION_KEY_RECEIVED,
            ConnectionState.REQUESTING_AUTH_STATUS,
            ConnectionState.AUTH_STATUS_RECEIVED,
            ConnectionState.AUTHENTICATING,
        ]

    def is_error(self):
        return (
            self
            in [
                ConnectionState.ERROR_MAX_RECONNECT_ATTEMPTS_REACHED,
                ConnectionState.ERROR_AUTH_FAILED,
                ConnectionState.ERROR_TOO_MANY_ERRORS,
                ConnectionState.ERROR_UNKNOWN,
            ]
            or self.connection_error()
        )

    def authenticated(self):
        return self is ConnectionState.AUTHENTICATED

    def is_terminal(self):
        return (
            self
            in [
                ConnectionState.AUTHENTICATED,
                ConnectionState.DISCONNECTED,
                ConnectionState.NOT_CONNECTED,
            ]
            or self.is_error()
        )


class Connection:
    """
    Connection object manages client creation, authentification and sends the packets
    to parse back
    """

    NOTIFY_CHARACTERISTIC = "00000003-0000-1000-8000-00805f9b34fb"
    WRITE_CHARACTERISTIC = "00000002-0000-1000-8000-00805f9b34fb"

    def __init__(
        self,
        ble_dev: BLEDevice,
        dev_sn: str,
        user_id: str,
        data_parse: Callable[[Packet], Awaitable[bool]],
        packet_parse: Callable[[bytes], Awaitable[Packet]],
        on_state_change: Callable[[ConnectionState], None] = lambda _: None,
        packet_version: int = 0x03,
    ) -> None:
        self._ble_dev = ble_dev
        self._address = ble_dev.address
        self._dev_sn = dev_sn
        self._user_id = user_id

        self._data_parse = data_parse
        self._packet_parse = packet_parse
        self._authenticated = False

        self._packet_version = packet_version

        self._errors = 0
        self._client = None
        self._connected = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._retry_on_disconnect = False
        self._retry_on_disconnect_delay = 10
        self._enc_packet_buffer = b""

        self._tasks: set[asyncio.Task] = set()
        self._debug_mode = False

        self._logger = ConnectionLogger(self)

        self._state_exception: Exception | type[Exception] | None = None
        self._last_exception: Exception | type[Exception] | None = None
        self._on_state_change = on_state_change
        self._state_changed = asyncio.Event()
        self._reconnect_task: asyncio.Task | None = None
        self._connection_attempt: int = 0
        self._reconnect_attempt: int = 0
        self._reconnect = True

        self._disconnect_listeners: list[DisconnectListener] = []
        self._connection_state = None
        self._set_state(ConnectionState.CREATED)

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

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
        self._disconnect_listeners.append(listener)

        def _unlisten():
            self._disconnect_listeners.remove(listener)

        return _unlisten

    def _notify_disconnect(self, exception: Exception | type[Exception] | None = None):
        if exception is None:
            exception = self._last_exception

        for listener in self._disconnect_listeners:
            listener(exception)

    def ble_dev(self) -> BLEDevice:
        return self._ble_dev

    def with_logging_options(self, options: LogOptions):
        self._logger.set_options(options)
        return self

    def with_disabled_reconnect(self, is_disabled: bool = True):
        self._reconnect = not is_disabled
        return self

    async def connect(
        self,
        max_attempts: int = MAX_CONNECT_ATTEMPTS,
        timeout: int = 20,
    ):
        if self._state.is_connecting():
            return

        self._connection_attempt += 1
        if self._connection_attempt > MAX_CONNECTION_ATTEMPTS:
            self._connection_attempt = 0
            self._notify_disconnect(self._last_exception)
            raise MaxConnectionAttemptsReached(
                last_error=self._last_exception,
                attempts=MAX_CONNECTION_ATTEMPTS,
            )

        self._connected.clear()
        self._disconnected.clear()

        error = None
        try:
            if self.is_connected:
                self._logger.warning("Device is already connected")
                return

            self._set_state(ConnectionState.ESTABLISHING_CONNECTION)
            self._logger.info("Connecting to device")
            self._client = await establish_connection(
                BleakClient,
                self.ble_dev(),
                self._ble_dev.name,
                disconnected_callback=self.disconnected,
                ble_device_callback=self.ble_dev,
                max_attempts=max_attempts,
                timeout=timeout,
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
            self.disconnected()
            return

        self._logger.info("Connected")
        self._errors = 0
        self._retry_on_disconnect = self._reconnect

        if self._client._backend.__class__.__name__ == "BleakClientBlueZDBus":
            await self._client._backend._acquire_mtu()

        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "MTU: %d", self._client.mtu_size
        )
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
        self._set_state(ConnectionState.DISCONNECTED)

    async def wait_connected(self, timeout: int = 20):
        """Will release when connection is happened and authenticated"""
        last_state = self._state
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

    async def wait_until_authenticated_or_error(self, raise_on_error: bool = False):
        while not self._state.is_terminal():
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
            return self._last_state

        return self._state

    async def wait_disconnected(self):
        """Will release when client got disconnected from the device"""
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

    @property
    def _state(self) -> ConnectionState:
        return self._connection_state

    @_state.setter
    def _state(self, value: ConnectionState):
        self._connection_state = value
        self._state_changed.set()
        self._state_changed.clear()
        self._on_state_change(value)

    def _set_state(
        self, state: ConnectionState, exc: Exception | type[Exception] | None = None
    ):
        self._state_exception = exc
        if exc is not None:
            self._last_exception = exc

        self._last_state = self._state
        self._state = state

        if state.is_error():
            self._notify_disconnect(exc)

    # En/Decrypt functions must create AES object every time, because
    # it saves the internal state after encryption and become useless
    async def decryptShared(self, encrypted_payload: str):
        aes_shared = AES.new(self._shared_key, AES.MODE_CBC, self._iv)
        return unpad(aes_shared.decrypt(encrypted_payload), AES.block_size)

    async def decryptSession(self, encrypted_payload: str):
        aes_session = AES.new(self._session_key, AES.MODE_CBC, self._iv)
        return unpad(aes_session.decrypt(encrypted_payload), AES.block_size)

    async def encryptSession(self, payload: str):
        aes_session = AES.new(self._session_key, AES.MODE_CBC, self._iv)
        return aes_session.encrypt(pad(payload, AES.block_size))

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

    async def parseSimple(self, data: str):
        """Deserializes bytes stream into the simple bytes"""
        self._logger.log_filtered(
            LogOptions.ENCRYPTED_PAYLOADS,
            "parseSimple: Data: %r",
            bytearray(data).hex(),
        )

        header = data[0:6]
        data_end = 6 + struct.unpack("<H", header[4:6])[0]
        payload_data = data[6 : data_end - 2]
        payload_crc = data[data_end - 2 : data_end]

        # Check the payload CRC16
        if crc16(header + payload_data) != struct.unpack("<H", payload_crc)[0]:
            error_msg = (
                "parseSimple: Unable to parse simple packet - incorrect CRC16: %r"
            )
            payload_hex = bytearray(payload_data).hex()
            self._logger.error(error_msg, payload_hex)
            raise PacketParseError

        return payload_data

    async def parseEncPackets(self, data: str) -> list[Packet]:
        """Deserializes bytes stream into a list of Packets"""
        # In case there are leftovers from previous processing - adding them to current
        # data
        if self._enc_packet_buffer:
            data = self._enc_packet_buffer + data
            self._enc_packet_buffer = b""

        self._logger.log_filtered(
            LogOptions.ENCRYPTED_PAYLOADS,
            "parseEncPackets: Data: %r",
            bytearray(data).hex(),
        )
        if len(data) < 8:
            error_msg = (
                "parseEncPackets: Unable to parse encrypted packet - too small: %r"
            )
            self._logger.error(error_msg, bytearray(data).hex())
            raise EncPacketParseError

        # Data can contain multiple EncPackets and even incomplete ones, so walking
        # through
        packets = []
        while data:
            if not data.startswith(EncPacket.PREFIX):
                error_msg = (
                    "parseEncPackets: Unable to parse encrypted packet - prefix is "
                    "incorrect: %r"
                )
                self._logger.error(error_msg, bytearray(data).hex())
                return packets

            header = data[0:6]
            data_end = 6 + struct.unpack("<H", header[4:6])[0]
            if data_end > len(data):
                self._enc_packet_buffer += data
                break

            payload_data = data[6 : data_end - 2]
            payload_crc = data[data_end - 2 : data_end]

            # Move to next data packet
            data = data[data_end:]

            try:
                # Check the packet CRC16
                if crc16(header + payload_data) != struct.unpack("<H", payload_crc)[0]:
                    error_msg = "Unable to parse encrypted packet - incorrect CRC16: %r"
                    self._logger.error(error_msg, bytearray(payload_data).hex())
                    raise PacketParseError  # noqa: TRY301

                # Decrypt the payload packet
                payload = await self.decryptSession(payload_data)
                self._logger.log_filtered(
                    LogOptions.DECRYPTED_PAYLOADS,
                    "parseEncPackets: decrypted payload: %r",
                    bytearray(payload).hex(),
                )

                # Parse packet
                packet = await self._packet_parse(payload)
                self._logger.log_filtered(
                    LogOptions.PACKETS,
                    "Parsed packet: %s",
                    packet,
                )
                if packet is not None:
                    packets.append(packet)
            except Exception as e:  # noqa: BLE001
                await self.add_error(e)

        return packets

    async def sendRequest(self, send_data: bytes, response_handler=None):
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "Sending: %r", bytearray(send_data).hex()
        )
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

    async def _sendRequest(self, send_data: bytes, response_handler=None):
        # Make sure the connection is here, otherwise just skipping
        if self._client is None or not self._client.is_connected:
            self._logger.log_filtered(
                LogOptions.CONNECTION_DEBUG,
                "Skip sending: disconnected: %r",
                bytearray(send_data).hex(),
            )
            return

        if response_handler:
            await self._client.start_notify(
                Connection.NOTIFY_CHARACTERISTIC, response_handler
            )
        await self._client.write_gatt_char(
            Connection.WRITE_CHARACTERISTIC, bytearray(send_data)
        )

    async def sendPacket(self, packet: Packet, response_handler=None):
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "Sending packet: %r", packet
        )
        # Wrapping and encrypting with session key
        to_send = EncPacket(
            EncPacket.FRAME_TYPE_PROTOCOL,
            EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
            packet.toBytes(),
            0,
            0,
            self._session_key,
            self._iv,
        ).toBytes()

        await self.sendRequest(to_send, response_handler)

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
        self._set_state(ConnectionState.PUBLIC_KEY_EXCHANGE)
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "initBleSessionKey: Pub key exchange"
        )
        self._private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP160r1)
        self._public_key = self._private_key.get_verifying_key()

        to_send = EncPacket(
            EncPacket.FRAME_TYPE_COMMAND,
            EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
            # Payload contains some weird prefix and generated public key
            b"\x01\x00" + self._public_key.to_string(),
        ).toBytes()

        # Device public key is sent as response, process will continue on device
        # response in handler
        await self.sendRequest(to_send, self.initBleSessionKeyHandler)

    async def initBleSessionKeyHandler(
        self, characteristic: BleakGATTCharacteristic, recv_data: bytearray
    ):
        if self._client is None or not self._client.is_connected:
            return

        self._set_state(ConnectionState.PUBLIC_KEY_RECEIVED)
        await self._client.stop_notify(Connection.NOTIFY_CHARACTERISTIC)

        data = await self.parseSimple(bytes(recv_data))
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
        self._shared_key = ecdsa.ECDH(
            ecdsa.SECP160r1, self._private_key, self._dev_pub_key
        ).generate_sharedsecret_bytes()
        # Set Initialization Vector from digest of the original shared key
        self._iv = hashlib.md5(self._shared_key).digest()
        if len(self._shared_key) > 16:
            # Using just 16 bytes of generated shared key
            self._shared_key = self._shared_key[0:16]

        await self.getKeyInfoReq()

    async def getKeyInfoReq(self):
        self._set_state(ConnectionState.REQUESTING_SESSION_KEY)
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "getKeyInfoReq: Receiving session key"
        )
        to_send = EncPacket(
            EncPacket.FRAME_TYPE_COMMAND,
            EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
            b"\x02",  # command to get key info to make the shared key
        ).toBytes()

        await self.sendRequest(to_send, self.getKeyInfoReqHandler)

    async def getKeyInfoReqHandler(
        self, characteristic: BleakGATTCharacteristic, recv_data: bytearray
    ):
        if self._client is None or not self._client.is_connected:
            return

        self._set_state(ConnectionState.SESSION_KEY_RECEIVED)
        await self._client.stop_notify(Connection.NOTIFY_CHARACTERISTIC)
        encrypted_data = await self.parseSimple(bytes(recv_data))

        if encrypted_data[0] != 0x02:
            raise AuthFailedError(
                "Received type of KeyInfo is != 0x02, need to dig into: "
                + encrypted_data.hex()
            )

        # Skipping the first byte - type of the payload (0x02)
        data = await self.decryptShared(encrypted_data[1:])

        # Parse the data that contains sRand (first 16 bytes) & seed (last 2 bytes)
        self._session_key = await self.genSessionKey(data[16:18], data[:16])

        await self.getAuthStatus()

    async def getAuthStatus(self):
        self._set_state(ConnectionState.REQUESTING_AUTH_STATUS)
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "getKeyInfoReq: Receiving auth status"
        )

        packet = Packet(0x21, 0x35, 0x35, 0x89, b"", 0x01, 0x01, self._packet_version)

        await self.sendPacket(packet, self.getAuthStatusHandler)

    async def getAuthStatusHandler(
        self, characteristic: BleakGATTCharacteristic, recv_data: bytearray
    ):
        if self._client is None or not self._client.is_connected:
            return

        self._set_state(ConnectionState.AUTH_STATUS_RECEIVED)
        await self._client.stop_notify(Connection.NOTIFY_CHARACTERISTIC)
        packets = await self.parseEncPackets(bytes(recv_data))
        if len(packets) < 1:
            raise PacketReceiveError
        data = packets[0].payload

        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG,
            "getAuthStatusHandler: data: %r",
            bytearray(data).hex(),
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
            0x21, 0x35, 0x35, 0x86, payload, 0x01, 0x01, self._packet_version
        )

        # Sending request and starting the common listener
        await self.sendPacket(packet, self.listenForDataHandler)

    async def listenForDataHandler(
        self, characteristic: BleakGATTCharacteristic, recv_data: bytearray
    ):
        try:
            packets = await self.parseEncPackets(bytes(recv_data))
        except Exception as e:  # noqa: BLE001
            await self.add_error(e)
            return

        for packet in packets:
            processed = False

            # Handling autoAuthentication response
            if packet.src == 0x35 and packet.cmdSet == 0x35 and packet.cmdId == 0x86:
                if packet.payload != b"\x00":
                    # TODO: Most probably we need to follow some other way for auth, but
                    # happens rarely
                    error_msg = "Auth failed with response: %r"
                    self._logger.error(error_msg, packet)
                    exc = AuthFailedError(error_msg % packet)
                    self._set_state(ConnectionState.ERROR_AUTH_FAILED, exc)

                    if self._client is not None and self._client.is_connected:
                        await self._client.disconnect()

                    raise exc

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

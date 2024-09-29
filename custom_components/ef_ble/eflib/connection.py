import struct
import asyncio
import logging
from collections.abc import Callable

from bleak import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak_retry_connector import (
    MAX_CONNECT_ATTEMPTS,
    BleakClientWithServiceCache,
    BLEDevice,
    establish_connection,
)

import hashlib
import ecdsa
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from .crc import crc16
from .packet import Packet
from .encpacket import EncPacket
from . import keydata

_LOGGER = logging.getLogger(__name__)

class PacketParseError:
    """Error during parsing Packet"""
class EncPacketParseError:
    """Error during parsing EncPacket"""
class PacketReceiveError:
    """Error during receiving packet"""
class AuthFailedError:
    """Error during authentificating"""

class Connection:
    '''Connection object manages client creation, authentification and sends the packets to parse back'''
    NOTIFY_CHARACTERISTIC = "00000003-0000-1000-8000-00805f9b34fb"
    WRITE_CHARACTERISTIC = "00000002-0000-1000-8000-00805f9b34fb"

    def __init__(self, ble_dev: BLEDevice, dev_sn: str, user_id: str, data_parse: Callable[[Packet], bool]) -> None:
        self._ble_dev = ble_dev
        self._address = ble_dev.address
        self._dev_sn = dev_sn
        self._user_id = user_id
        self._data_parse = data_parse

        self._client = None
        self._disconnected = asyncio.Event()
        self._retry_on_disconnect = True

        self._enc_packet_buffer = b''

    @property
    def is_connected(self) -> bool:
        return self._client != None and self._client.is_connected

    def ble_dev(self) -> BLEDevice:
        return self._ble_dev

    async def connect(self, max_attempts: int = MAX_CONNECT_ATTEMPTS):
        self._retry_on_disconnect = True
        try:
            if self._client != None:
                if self._client.is_connected:
                    _LOGGER.warning("%s: Device is already connected", self._address)
                    return
                _LOGGER.info("%s: Reconnecting to device", self._address)
                await self._client.connect()
            else:
                _LOGGER.info("%s: Connecting to device", self._address)
                self._client = await establish_connection(
                    BleakClientWithServiceCache,
                    self.ble_dev(),
                    self._ble_dev.name,
                    disconnected_callback=self.disconnected,
                    ble_device_callback=self.ble_dev,
                    max_attempts=max_attempts,
                )
        except (asyncio.TimeoutError, BleakError) as err:
            _LOGGER.error("%s: Failed to connect to the device: %s", self._address, err)
            raise err

        _LOGGER.info("%s: Connected", self._address)

        if self._client._backend.__class__.__name__ == "BleakClientBlueZDBus":
            await self._client._backend._acquire_mtu()
        _LOGGER.debug("%s: MTU: %d", self._address, self._client.mtu_size)

        _LOGGER.info("%s: Init completed, starting auth routine...", self._address)

        await self.initBleSessionKey()

    def disconnected(self, *args, **kwargs) -> None:
        _LOGGER.info("%s: Disconnected from device", self._address)
        if self._retry_on_disconnect:
            loop = asyncio.get_event_loop()
            loop.create_task(self.connect())
        else:
            self._disconnected.set()

    async def disconnect(self):
        _LOGGER.info("%s: Disconnecting from device", self._address)
        self._retry_on_disconnect = False
        if self._client != None:
            await self._client.disconnect()

    async def waitDisconnect(self):
        await self._disconnected.wait()

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
        '''Implements the necessary part of the logic, rest is skipped'''
        data_num = [0, 0, 0, 0]

        # Using seed and predefined key to get first 2 numbers
        pos = seed[0] * 0x10 + ((seed[1] - 1) & 0xff) * 0x100
        data_num[0] = struct.unpack('<Q', keydata.get8bytes(pos))[0]
        pos += 8
        data_num[1] = struct.unpack('<Q', keydata.get8bytes(pos))[0]

        # Getting the last 2 numbers from srand
        srand_len = len(srand)
        lower_srand_len = srand_len & 0xffffffff
        if srand_len < 0x20:
            srand_len = 0
        else:
            raise Exception("Not implemented")

        # Just putting srand in there byte-by-byte
        data_num[2] = struct.unpack('<Q', srand[0:8])[0]
        data_num[3] = struct.unpack('<Q', srand[8:16])[0]

        # Converting data numbers to 32 bytes
        data = b''
        data += struct.pack('<Q', data_num[0])
        data += struct.pack('<Q', data_num[1])
        data += struct.pack('<Q', data_num[2])
        data += struct.pack('<Q', data_num[3])

        # Hashing data to get the session key
        session_key = hashlib.md5(data).digest()

        return session_key

    async def parseSimple(self, data: str):
        '''Deserializes bytes stream into the simple bytes'''
        _LOGGER.debug("%s: parseSimple: Data: %r", self._address, " ".join("{:02x}".format(c) for c in data))

        header = data[0:6]
        data_end = 6 + struct.unpack('<H', header[4:6])[0]
        payload_data = data[6:data_end-2]
        payload_crc = data[data_end-2:data_end]

        # Check the payload CRC16
        if crc16(header+payload_data) != struct.unpack('<H', payload_crc)[0]:
            _LOGGER.error("%s: parseSimple: Unable to parse simple packet - incorrect CRC16: %r", self._address, " ".join("{:02x}".format(c) for c in data[:6+payload_length]))
            raise PacketParseError

        return payload_data

    async def parseEncPackets(self, data: str):
        '''Deserializes bytes stream into a list of Packets'''
        # In case there are leftovers from previous processing - adding them to current data
        if self._enc_packet_buffer:
            data = self._enc_packet_buffer + data
            self._enc_packet_buffer = b''

        _LOGGER.debug("%s: parseEncPackets: Data: %r", self._address, " ".join("{:02x}".format(c) for c in data))
        if len(data) < 8:
            _LOGGER.error("%s: parseEncPackets: Unable to parse encrypted packet - too small: %r", self._address, " ".join("{:02x}".format(c) for c in data))
            raise EncPacketParseError

        # Data can contain multiple EncPackets and even incomplete ones, so walking through
        packets = list()
        while data:
            if not data.startswith(EncPacket.PREFIX):
                _LOGGER.error("%s: parseEncPackets: Unable to parse encrypted packet - prefix is incorrect: %r", self._address, " ".join("{:02x}".format(c) for c in data))
                return packets

            header = data[0:6]
            data_end = 6 + struct.unpack('<H', header[4:6])[0]
            if data_end > len(data):
                self._enc_packet_buffer += data
                break

            payload_data = data[6:data_end-2]
            payload_crc = data[data_end-2:data_end]

            # Move to next data packet
            data = data[data_end:]

            # Check the packet CRC16
            if crc16(header+payload_data) != struct.unpack('<H', payload_crc)[0]:
                _LOGGER.error("%s: Unable to parse encrypted packet - incorrect CRC16: %r", self._address, " ".join("{:02x}".format(c) for c in data[:6+payload_length]))
                continue

            # Decrypt the payload packet
            payload = await self.decryptSession(payload_data)
            _LOGGER.debug("%s: parseEncPackets: decrypted payload: %r", self._address, " ".join("{:02x}".format(c) for c in payload))

            # Parse packet
            packet = Packet.fromBytes(payload)
            if packet != None:
                packets.append(packet)

        return packets

    async def sendRequest(self, send_data: bytes, response_handler):
        _LOGGER.debug("%s: Sending: %r", self._address, " ".join("{:02x}".format(c) for c in send_data))
        await self._client.start_notify(Connection.NOTIFY_CHARACTERISTIC, response_handler)
        await self._client.write_gatt_char(Connection.WRITE_CHARACTERISTIC, bytearray(send_data))

    async def initBleSessionKey(self):
        _LOGGER.debug("%s: initBleSessionKey: Pub key exchange", self._address)
        self._private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP160r1)
        self._public_key = self._private_key.get_verifying_key()

        to_send = EncPacket(
            EncPacket.FRAME_TYPE_COMMAND, EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
            # Payload contains some weird prefix and generated public key
            b'\x01\x00' + self._public_key.to_string(),
        ).toBytes()

        # Device public key is sent as response, process will continue on device response in handler
        await self.sendRequest(to_send, self.initBleSessionKeyHandler)

    async def initBleSessionKeyHandler(self, characteristic: BleakGATTCharacteristic, recv_data: bytearray):
        await self._client.stop_notify(Connection.NOTIFY_CHARACTERISTIC)

        data = await self.parseSimple(bytes(recv_data))
        status = data[1]
        ecdh_type_size = getEcdhTypeSize(data[2])
        self._dev_pub_key = ecdsa.VerifyingKey.from_string(data[3:ecdh_type_size+3], curve=ecdsa.SECP160r1)

        # Generating shared key from our private key and received device public key
        # NOTE: The device will do the same with it's private key and our public key to generate the
        # same shared key value and use it to encrypt/decrypt using symmetric encryption algorithm
        self._shared_key = ecdsa.ECDH(ecdsa.SECP160r1, self._private_key, self._dev_pub_key).generate_sharedsecret_bytes()
        # Set Initialization Vector from digest of the original shared key
        self._iv = hashlib.md5(self._shared_key).digest()
        if len(self._shared_key) > 16:
            # Using just 16 bytes of generated shared key
            self._shared_key = self._shared_key[0:16]

        await self.getKeyInfoReq()

    async def getKeyInfoReq(self):
        _LOGGER.debug("%s: getKeyInfoReq: Receiving session key", self._address)
        to_send = EncPacket(
            EncPacket.FRAME_TYPE_COMMAND, EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
            b'\x02',  # command to get key info to make the shared key
        ).toBytes()

        await self.sendRequest(to_send, self.getKeyInfoReqHandler)

    async def getKeyInfoReqHandler(self, characteristic: BleakGATTCharacteristic, recv_data: bytearray):
        await self._client.stop_notify(Connection.NOTIFY_CHARACTERISTIC)
        encrypted_data = await self.parseSimple(bytes(recv_data))

        if encrypted_data[0] != 0x02:
            raise Exception("Received type of KeyInfo is != 0x02, need to dig into: " + encrypted_data.hex())

        # Skipping the first byte - type of the payload (0x02)
        data = await self.decryptShared(encrypted_data[1:])

        # Parse the data that contains sRand (first 16 bytes) & seed (last 2 bytes)
        self._session_key = await self.genSessionKey(data[16:18], data[:16])

        await self.getAuthStatus()

    async def getAuthStatus(self):
        _LOGGER.debug("%s: getKeyInfoReq: Receiving auth status", self._address)

        # Preparing packet with empty payload
        packet = Packet(0x21, 0x35, 0x35, 0x89, b'', 0x01, 0x01, 0x03, 0x00, 0x00)

        # Wrapping and encrypting with session key
        to_send = EncPacket(
            EncPacket.FRAME_TYPE_PROTOCOL, EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
            packet.toBytes(), 0, 0, 0, self._session_key, self._iv,
        ).toBytes()

        await self.sendRequest(to_send, self.getAuthStatusHandler)

    async def getAuthStatusHandler(self, characteristic: BleakGATTCharacteristic, recv_data: bytearray):
        await self._client.stop_notify(Connection.NOTIFY_CHARACTERISTIC)
        packets = await self.parseEncPackets(bytes(recv_data))
        if len(packets) < 1:
            raise PacketReceiveError
        data = packets[0].payload()

        _LOGGER.debug("%s: getAuthStatusHandler: data: %r", self._address, " ".join("{:02x}".format(c) for c in data))
        await self.autoAuthentication()

    async def autoAuthentication(self):
        _LOGGER.debug("%s: autoAuthentication: Sending secretKey consists of user id and device serial number", self._address)

        # Building payload for auth
        md5_data = hashlib.md5((self._user_id + self._dev_sn).encode('ASCII')).digest()
        payload = ("".join("{:02X}".format(c) for c in md5_data)).encode('ASCII')

        # Forming packet
        packet = Packet(0x21, 0x35, 0x35, 0x86, payload, 0x01, 0x01, 0x03, 0x00, 0x00)

        # Wrapping and encrypting with session key
        to_send = EncPacket(
            EncPacket.FRAME_TYPE_PROTOCOL, EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
            packet.toBytes(), 0, 0, 0, self._session_key, self._iv,
        ).toBytes()

        await self.sendRequest(to_send, self.autoAuthenticationHandler)

    async def autoAuthenticationHandler(self, characteristic: BleakGATTCharacteristic, recv_data: bytearray):
        await self._client.stop_notify(Connection.NOTIFY_CHARACTERISTIC)
        packets = await self.parseEncPackets(bytes(recv_data))

        if len(packets) < 1:
            raise PacketReceiveError

        data = packets[0].payload()
        _LOGGER.debug("%s: autoAuthenticationHandler: data: %r", self._address, " ".join("{:02x}".format(c) for c in data))

        if data != b'\x00':
            _LOGGER.error("%s: Auth failed with response: %r", self._address, " ".join("{:02x}".format(c) for c in data))
            raise AuthFailedError

        await self.listenForData()

    async def listenForData(self):
        _LOGGER.info("%s: listenForData: Listening for data from device", self._address)

        await self._client.start_notify(Connection.NOTIFY_CHARACTERISTIC, self.listenForDataHandler)

    async def listenForDataHandler(self, characteristic: BleakGATTCharacteristic, recv_data: bytearray):
        packets = await self.parseEncPackets(bytes(recv_data))

        for packet in packets:
            processed = await self._data_parse(packet)
            if not processed:
                _LOGGER.debug("%s: listenForDataHandler: packet src: %02X, cmdSet: %02X, cmdId: %02X", self._address, packet.src(), packet.cmdSet(), packet.cmdId())
                _LOGGER.debug("%s: listenForDataHandler: packet data: %r", self._address, " ".join("{:02x}".format(c) for c in packet.payload()))

def getEcdhTypeSize(curve_num: int):
    '''Returns size of ecdh based on type'''
    match curve_num:
        case 1:
            return 52
        case 2:
            return 56
        case 3,4:
            return 64
        case _:
            return 40

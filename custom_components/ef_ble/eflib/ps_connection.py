"""PowerStream BLE connection using MD5-derived keys instead of ECDH."""

import hashlib
import struct

from Crypto.Cipher import AES

from .connection import Connection
from .crc import crc8
from .logging_util import LogOptions
from .packet import Packet


class PowerStreamConnection(Connection):
    """
    Connection for PowerStream devices.

    Key differences from the base ECDH connection:
    - Session key = MD5(serial), IV = MD5(reversed serial)
    - No EncPacket wrapper — Packet header (5 bytes) stays plaintext
    - Zero-padding instead of PKCS7 for AES-CBC encryption
    - Skips ECDH key exchange — goes straight to autoAuthentication
    - Handles V19 plaintext data pushes alongside V2 encrypted packets
    """

    async def initBleSessionKey(self):
        serial = self._dev_sn
        self._session_key = hashlib.md5(serial.encode()).digest()
        self._iv = hashlib.md5(serial[::-1].encode()).digest()
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG,
            "initBleSessionKey: Derived keys from serial",
        )
        # Skip getAuthStatus — device pushes V19 data unsolicited which breaks
        # the single-shot handler. Go straight to autoAuthentication which uses
        # the persistent listenForDataHandler.
        await self.autoAuthentication()

    async def encryptSession(self, payload):
        padded_len = (len(payload) + 15) // 16 * 16
        padded = payload + b"\x00" * (padded_len - len(payload))
        aes_session = AES.new(self._session_key, AES.MODE_CBC, self._iv)
        return aes_session.encrypt(padded)

    async def decryptSession(self, encrypted_payload):
        aes_session = AES.new(self._session_key, AES.MODE_CBC, self._iv)
        return aes_session.decrypt(encrypted_payload)

    async def sendPacket(self, packet: Packet, response_handler=None):
        self._logger.log_filtered(
            LogOptions.CONNECTION_DEBUG, "Sending packet: %r", packet
        )
        raw = packet.toBytes()
        header = raw[:5]
        inner = raw[5:]
        encrypted = await self.encryptSession(inner)
        await self.sendRequest(header + encrypted, response_handler)

    async def parseEncPackets(self, data: str) -> list[Packet]:
        """
        Deserialise BLE data into Packets for PowerStream wire format.

        Handles two packet types:
        - V2 encrypted: plaintext 5-byte header + AES-CBC encrypted body
        - V19 plaintext: entire packet is unencrypted (XOR handled by Packet.fromBytes)
        """
        if self._enc_packet_buffer:
            data = self._enc_packet_buffer + data
            self._enc_packet_buffer = b""

        self._logger.log_filtered(
            LogOptions.ENCRYPTED_PAYLOADS,
            "parseEncPackets: Data: %r",
            bytearray(data).hex(),
        )

        packets = []
        while data:
            start = data.find(Packet.PREFIX)
            if start < 0:
                break
            if start > 0:
                data = data[start:]

            if len(data) < 5:
                self._enc_packet_buffer = data
                break

            if crc8(data[:4]) != data[4]:
                data = data[1:]
                continue

            payload_length = struct.unpack("<H", data[2:4])[0]
            version = data[1]

            if version == 0x13:
                # V19 packets are plaintext (not AES-encrypted).
                # Layout: header(5) + inner(13) + payload — no CRC16.
                total_len = 18 + payload_length
                if len(data) < total_len:
                    self._enc_packet_buffer = data
                    break

                full_packet = data[:total_len]
                data = data[total_len:]
            else:
                # V2/V3 encrypted packets: header stays plaintext, body is AES-CBC
                inner_overhead = 15 if version >= 3 else 13
                inner_len = inner_overhead + payload_length
                encrypted_len = (inner_len + 15) // 16 * 16
                frame_len = 5 + encrypted_len

                if len(data) < frame_len:
                    self._enc_packet_buffer = data
                    break

                header = data[:5]
                encrypted_body = data[5:frame_len]
                data = data[frame_len:]

                decrypted = await self.decryptSession(encrypted_body)
                full_packet = header + decrypted[:inner_len]

            try:
                self._on_packet_data_received(full_packet)
                packet = await self._packet_parse(full_packet)
                self._on_packet_parsed(packet)
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

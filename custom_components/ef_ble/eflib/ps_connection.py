"""PowerStream BLE connection using MD5-derived keys instead of ECDH."""

import asyncio
import hashlib
import struct

from Crypto.Cipher import AES

from .connection import AuthFailedError, Connection, ConnectionState
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
    - Skips ECDH key exchange — sends getAuthStatus then autoAuthentication
    - Both V3 (auth/config) and V13 (telemetry) frames are AES-CBC encrypted
    - V13 payload is additionally XOR'd with seq[0] (handled by Packet.fromBytes)
    """

    _HEARTBEAT_REQUEST_INTERVAL = 30

    async def initBleSessionKey(self):
        serial = self._dev_sn
        self._session_key = hashlib.md5(serial.encode()).digest()
        self._iv = hashlib.md5(serial[::-1].encode()).digest()

        await self._client.start_notify(
            Connection.NOTIFY_CHARACTERISTIC, self.listenForDataHandler
        )

        # Send getAuthStatus to wake the device before authenticating.
        await self._send_auth_status()
        await asyncio.sleep(2)

        await self.autoAuthentication()

    async def _send_auth_status(self):
        pkt = Packet(0x21, 0x35, 0x35, 0x89, b"", 0x01, 0x01, 0x03)
        await self.sendPacket(pkt)

    async def _heartbeat_request_loop(self):
        """Periodically send getAuthStatus to trigger cmdId=0x01 heartbeats."""
        while self._client is not None and self._client.is_connected:
            await asyncio.sleep(self._HEARTBEAT_REQUEST_INTERVAL)
            try:
                await self._send_auth_status()
                self._logger.info("Heartbeat request sent")
            except Exception as e:  # noqa: BLE001
                self._logger.warning("Heartbeat request failed: %s", e)
                continue

    async def listenForDataHandler(self, characteristic, recv_data):
        try:
            packets = await self.parseEncPackets(bytes(recv_data))
        except Exception as e:  # noqa: BLE001
            await self.add_error(e)
            return
        for packet in packets:
            processed = False
            if packet.src == 0x35 and packet.cmdSet == 0x35 and packet.cmdId == 0x86:
                if packet.payload != b"\x00":
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
                task = asyncio.create_task(self._heartbeat_request_loop())
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            else:
                try:
                    processed = await self._data_parse(packet)
                except Exception as e:  # noqa: BLE001
                    await self.add_error(e)
                    continue
            if not processed:
                self._logger.debug("Unhandled packet: %r", packet)

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
        # Write directly with Write Without Response (response=False).
        # Notifications are subscribed once in initBleSessionKey.
        # response=False avoids the 20s hang when the device doesn't
        # support Write With Response on this characteristic.
        if self._client is not None and self._client.is_connected:
            await self._client.write_gatt_char(
                Connection.WRITE_CHARACTERISTIC,
                bytearray(header + encrypted),
                response=False,
            )

    async def parseEncPackets(self, data: str) -> list[Packet]:
        """
        Deserialise BLE data into Packets for PowerStream wire format.

        All frames (V2, V3, V13) share the same encrypted layout:
          header(5B plaintext) + AES-CBC(zero_pad(inner))

        V13 payload is additionally XOR'd with seq[0] by the device firmware;
        Packet.fromBytes handles that transparently.
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

            # Inner overhead: V3/V13 have dsrc+ddst (15 bytes), V2 does not (13 bytes).
            # The 15 includes 2 bytes for CRC16 (V3) or padding (V13).
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

            try:
                decrypted = await self.decryptSession(encrypted_body)
                full_packet = header + decrypted[:inner_len]

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

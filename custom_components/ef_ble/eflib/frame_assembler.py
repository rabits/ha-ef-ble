import struct
from abc import ABC, abstractmethod

from .crc import crc8, crc16
from .encpacket import EncPacket
from .encryption import EncryptionStrategy
from .packet import Packet


class FrameAssembler(ABC):
    """Strategy for wire-level frame encoding and decoding"""

    def __init__(self, encryption: EncryptionStrategy) -> None:
        self._buffer = b""
        self._encryption = encryption

    @property
    @abstractmethod
    def write_with_response(self) -> bool:
        """Whether BLE writes should use write-with-response"""

    @abstractmethod
    async def encode(self, packet: Packet) -> bytes:
        """Encode a Packet into wire bytes (encrypted, framed)"""

    @abstractmethod
    async def reassemble(self, data: bytes) -> list[bytes]:
        """Decode wire bytes into decrypted payloads ready for Packet.from_bytes()"""


class EncPacketAssembler(FrameAssembler):
    """Frame assembler for encrypt_type 7: EncPacket wrapper (0x5A5A prefix, CRC16)"""

    @property
    def write_with_response(self) -> bool:
        return True

    async def encode(self, packet: Packet) -> bytes:
        return EncPacket(
            EncPacket.FRAME_TYPE_PROTOCOL,
            EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
            packet.to_bytes(),
            0,
            0,
            self._encryption.session_key,
            self._encryption.iv,
        ).to_bytes()

    async def reassemble(self, data: bytes) -> list[bytes]:
        if self._buffer:
            data = self._buffer + data
            self._buffer = b""

        payloads = []
        while data:
            start = data.find(EncPacket.PREFIX)
            if start < 0:
                data = b""
                break
            if start > 0:
                data = data[start:]

            if len(data) < 8:
                break

            header = data[0:6]
            payload_len = struct.unpack("<H", header[4:6])[0]

            # reject obviously corrupt length values instead of buffering
            if payload_len > 10_000:
                data = data[2:]
                continue

            data_end = 6 + payload_len
            if data_end > len(data):
                # could be a genuine incomplete frame, or a false prefix inside payload
                # data whose corrupted length extends past the buffer - check whether
                # another real prefix exists later in the data - if so, this one is
                # likely spurious
                next_prefix = data[2:].find(EncPacket.PREFIX)
                if next_prefix >= 0:
                    data = data[2 + next_prefix :]
                    continue
                # no other candidate - buffer for next notification
                break

            payload_data = data[6 : data_end - 2]
            payload_crc = data[data_end - 2 : data_end]

            if crc16(header + payload_data) != struct.unpack("<H", payload_crc)[0]:
                # CRC mismatch - this prefix was either inside payload or got corrupted
                data = data[2:]
                continue

            data = data[data_end:]
            decrypted = await self._encryption.decrypt(payload_data)
            payloads.append(decrypted)

        self._buffer = data
        return payloads


class PassthroughAssembler(FrameAssembler):
    """Frame assembler for encrypt_type 0: plain V3 packets, no outer encryption"""

    def __init__(self, encryption: EncryptionStrategy | None = None) -> None:
        super().__init__(encryption)  # type: ignore[arg-type]

    @property
    def write_with_response(self) -> bool:
        return False

    async def encode(self, packet: Packet) -> bytes:
        return packet.to_bytes()

    async def reassemble(self, data: bytes) -> list[bytes]:
        if self._buffer:
            data = self._buffer + data
            self._buffer = b""

        payloads: list[bytes] = []
        while data:
            start = data.find(Packet.PREFIX)
            if start < 0:
                data = b""
                break
            if start > 0:
                data = data[start:]

            if len(data) < 5:
                break

            if crc8(data[:4]) != data[4]:
                # not a valid header here - skip this byte and keep scanning
                data = data[1:]
                continue

            payload_length = struct.unpack("<H", data[2:4])[0]
            version_byte = data[1]

            if version_byte == 4:
                # V4: 8-byte outer header + payload + 2-byte CRC16
                frame_len = 8 + payload_length + 2
            else:
                # V2/V3: 5-byte header + inner-cmd block + payload + 2-byte CRC16
                inner_overhead = 15 if (version_byte & 0x0F) >= 3 else 13
                frame_len = 5 + inner_overhead + payload_length

            if len(data) < frame_len:
                break

            payloads.append(data[:frame_len])
            data = data[frame_len:]

        self._buffer = data
        return payloads


class RawHeaderAssembler(FrameAssembler):
    """Frame codec for encrypt_type 1: 5-byte plaintext header (0xAA) + AES body"""

    @property
    def write_with_response(self) -> bool:
        return False

    async def encode(self, packet: Packet) -> bytes:
        raw = packet.to_bytes()
        header = raw[:5]
        inner = raw[5:]
        encrypted = await self._encryption.encrypt(inner)
        return header + encrypted

    async def reassemble(self, data: bytes) -> list[bytes]:
        if self._buffer:
            data = self._buffer + data
            self._buffer = b""

        payloads = []
        while data:
            start = data.find(Packet.PREFIX)
            if start < 0:
                data = b""
                break

            if start > 0:
                data = data[start:]

            if len(data) < 5:
                break

            if crc8(data[:4]) != data[4]:
                data = data[1:]
                continue

            payload_length = struct.unpack("<H", data[2:4])[0]
            version = data[1]

            # Bytes after the 5-byte unencrypted header that are NOT payload_length:
            #   V4  (0x04): outer[5..7] (3 B) + CRC16 (2 B) = 5   (payload_length includes 8-B inner cmd)
            #   V3  (0x03): product+seq+zeros+addr+cmd (13 B) + CRC16 (2 B) = 15
            #   V19 (0x13): same 13-B cmd section; no CRC16; \xbb\xbb is inside payload_length = 13
            #   V2  (0x02): product+seq+zeros+addr+cmd (11 B) + CRC16 (2 B) = 13
            if version == 4:
                inner_overhead = 5
            elif version >= 3:
                inner_overhead = 15
            else:
                inner_overhead = 13
            inner_len = inner_overhead + payload_length
            encrypted_len = (inner_len + 15) // 16 * 16
            frame_len = 5 + encrypted_len

            if len(data) < frame_len:
                break

            header = data[:5]
            encrypted_body = data[5:frame_len]
            data = data[frame_len:]

            decrypted = await self._encryption.decrypt(encrypted_body)
            payloads.append(header + decrypted[:inner_len])

        self._buffer = data
        return payloads


class SimplePacketAssembler:
    """Assembler for unencrypted EncPacket command/response frames"""

    def __init__(self) -> None:
        self._buffer = b""

    @staticmethod
    def encode(payload: bytes) -> bytes:
        """Wrap raw payload bytes in an unencrypted EncPacket command frame"""
        return EncPacket(
            EncPacket.FRAME_TYPE_COMMAND,
            EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
            payload,
        ).to_bytes()

    def parse(self, data: bytes) -> bytes | None:
        """
        Extract the payload from one EncPacket frame, scanning for the prefix

        Returns the payload when a complete valid frame is found, or None when no frame
        is available yet and another BLE notification is expected to arrive: incomplete
        data, stale/foreign notification bytes with no frame prefix, or only CRC-invalid
        candidates. This assembler runs only during the auth handshake, where the right
        response to unparseable data is to wait for the next notification (and let the
        connection timeout bound a truly stuck device) rather than abort the handshake.
        """
        if self._buffer:
            data = self._buffer + data
            self._buffer = b""

        while data:
            start = data.find(EncPacket.PREFIX)
            if start < 0:
                return None
            if start > 0:
                data = data[start:]

            if len(data) < 8:
                self._buffer = data
                return None

            header = data[0:6]
            data_end = 6 + struct.unpack("<H", header[4:6])[0]

            if data_end > len(data):
                # could be incomplete or a false prefix inside payload data
                next_prefix = data[2:].find(EncPacket.PREFIX)
                if next_prefix >= 0:
                    data = data[2 + next_prefix :]
                    continue
                self._buffer = data
                return None

            payload_data = data[6 : data_end - 2]
            payload_crc = data[data_end - 2 : data_end]

            if crc16(header + payload_data) != struct.unpack("<H", payload_crc)[0]:
                data = data[2:]
                continue

            return payload_data

        # Loop only exits here when the data was fully consumed without yielding a frame
        # (all candidates were false prefixes / CRC failures). Wait for more data.
        return None

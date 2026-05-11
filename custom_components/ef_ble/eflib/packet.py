import logging
import struct
from dataclasses import dataclass
from typing import ClassVar, TypeGuard

from .crc import crc8, crc16

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Packet:
    """
    V2 / V3 / V19 packet codec

    V4 (version 0x04) is a different wire format and lives in `PacketV4`.
    """

    src: int
    dst: int
    cmd_set: int
    cmd_id: int
    payload: bytes = b""
    dsrc: int = 1
    ddst: int = 1
    version: int = 3
    seq: bytes = b"\x00\x00\x00\x00"
    product_id: int = 0

    PREFIX: ClassVar[bytes] = b"\xaa"
    NET_BLE_COMMAND_CMD_CHECK_RET_TIME: ClassVar[int] = 0x53
    NET_BLE_COMMAND_CMD_SET_RET_TIME: ClassVar[int] = 0x52

    @property
    def payload_hex(self) -> str:
        return self.payload.hex()

    @staticmethod
    def from_bytes(
        data: bytes, xor_payload: bool = False
    ) -> "Packet | PacketV4 | InvalidPacket":
        if not data.startswith(Packet.PREFIX):
            error_msg = "Unable to parse packet - prefix is incorrect: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        version = data[1]

        if version == 4:
            return PacketV4.from_bytes(data)

        if (version == 2 and len(data) < 18) or (
            version in [3, 0x13] and len(data) < 20
        ):
            error_msg = "Unable to parse packet - too small: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        payload_length = struct.unpack("<H", data[2:4])[0]

        # Version 19 (0x13, V4 protocol stack) has no CRC16 checksum
        if version in [2, 3]:
            if crc16(data[:-2]) != struct.unpack("<H", data[-2:])[0]:
                error_msg = "Unable to parse packet - incorrect CRC16: %s"
                _LOGGER.error(error_msg, bytearray(data).hex())
                return InvalidPacket(error_msg % bytearray(data).hex())

        # Check header CRC8
        if crc8(data[:4]) != data[4]:
            error_msg = "Unable to parse packet - incorrect header CRC8: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        # data[4] # crc8 of header
        # product_id = data[5] # We can't determine the product id from the bytestream

        # Seq is used for multiple purposes, so leaving as is
        seq = data[6:10]
        # data[10:12] # static zeroes in V2/V3; used differently in V19
        src = data[12]
        dst = data[13]

        dsrc = ddst = 0
        payload_start = 16 if version == 2 else 18

        if version == 2:
            cmd_set, cmd_id = data[14:payload_start]
        else:
            dsrc, ddst, cmd_set, cmd_id = data[14:payload_start]

        payload = b""
        if payload_length > 0:
            payload = data[payload_start : payload_start + payload_length]

            # If first byte of seq is set - we need to xor payload with it to get the
            # real data
            if xor_payload and seq[0] != 0:
                payload = bytes([c ^ seq[0] for c in payload])

            if version == 0x13 and payload[-2:] == b"\xbb\xbb":
                payload = payload[:-2]

        return Packet(
            src=src,
            dst=dst,
            cmd_set=cmd_set,
            cmd_id=cmd_id,
            payload=payload,
            dsrc=dsrc,
            ddst=ddst,
            version=version,
            seq=seq,
        )

    def to_bytes(self) -> bytes:
        """Serialize the internal data to bytes stream."""
        # Header
        data = Packet.PREFIX
        data += struct.pack("<B", self.version) + struct.pack("<H", len(self.payload))
        # Header crc
        data += struct.pack("<B", crc8(data))
        # Additional data
        data += self.product_byte() + self.seq
        data += b"\x00\x00"  # Unknown static zeroes, no strings attached right now

        data += struct.pack("<B", self.src) + struct.pack("<B", self.dst)

        # V3+ includes dsrc/ddst fields, V2 does not
        if self.version >= 0x03:
            data += struct.pack("<B", self.dsrc) + struct.pack("<B", self.ddst)

        data += struct.pack("<B", self.cmd_set) + struct.pack("<B", self.cmd_id)
        # Payload
        data += self.payload
        # Packet crc
        data += struct.pack("<H", crc16(data))

        return data

    def product_byte(self) -> bytes:
        """Return magic depending on product id."""
        if self.product_id >= 0:
            return b"\x0d"
        return b"\x0c"

    def __repr__(self) -> str:
        return (
            "Packet("
            f"src=0x{self.src:02X}, "
            f"dst=0x{self.dst:02X}, "
            f"cmd_set=0x{self.cmd_set:02X}, "
            f"cmd_id=0x{self.cmd_id:02X}, "
            f"payload=bytes.fromhex('{self.payload_hex}'), "
            f"dsrc=0x{self.dsrc:02X}, "
            f"ddst=0x{self.ddst:02X}, "
            f"version=0x{self.version:02X}, "
            f"seq={self.seq}, "
            f"product_id=0x{self.product_id:02X}"
            ")"
        )

    @staticmethod
    def is_invalid(
        packet: "Packet | PacketV4 | InvalidPacket",
    ) -> TypeGuard["InvalidPacket"]:
        """Check if the given packet is invalid."""
        return isinstance(packet, InvalidPacket)


@dataclass(slots=True)
class PacketV4:
    """
    V4 (version 0x04) packet codec

    Wire format:
      [0]      0xaa prefix
      [1]      version
      [2:3]    payload_length LE
      [4]      CRC8 of bytes 0..3 - also the XOR key for bytes [8:]
      [5]      type_byte: enc_type[7:5] | check_type[4:2] | is_rw_cmd[1] | is_ack[0]
      [6]      v4_type_a - part of V4 session info
      [7]      v4_type_b - layer-3 XOR key when non-zero

      [8]      cmd_flags  (inner cmd header byte 0, always has bit 5 set after XOR)
      [9]      frame_type
      [10]     payload_type
      [11]     time_snap_b0
      [12]     src
      [13]     dst
      [14]     cmd_set
      [15]     cmd_id
      [16:8+payload_length-1] data payload (for SHP3 - first 22 bytes is routing header)

      [8+payload_length:-1]   CRC16 LE  (computed over obfuscated bytes)

    Two layers of obfuscation are applied to the body:

    1. CRC8 layer (always applied) - every byte from position [8] onward (inner cmd
       header + payload) is XOR'd with the outer header CRC8 value at data[4]
    2. v4_type_b layer (applied to the application payload only when v4_type_b is
       non-zero)
    """

    src: int
    dst: int
    cmd_set: int
    cmd_id: int
    payload: bytes = b""
    enc_type: int = 0
    check_type: int = 0
    is_rw_cmd: bool = False
    is_ack: bool = False
    frame_type: int = 0
    payload_type: int = 0
    cmd_flags: int = 0x20
    v4_type_a: int = 0
    v4_type_b: int = 0
    time_snap_b0: int = 0

    PREFIX: ClassVar[bytes] = b"\xaa"
    VERSION: ClassVar[int] = 0x04

    @property
    def version(self) -> int:
        return self.VERSION

    @property
    def payload_hex(self) -> str:
        return self.payload.hex()

    @staticmethod
    def from_bytes(data: bytes) -> "PacketV4 | InvalidPacket":
        if len(data) < 18:
            error_msg = "Unable to parse packet - too small: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        payload_length = struct.unpack("<H", data[2:4])[0]

        if len(data) != 8 + payload_length + 2:
            error_msg = "Unable to parse packet - V4 length mismatch: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        if crc16(data[:-2]) != struct.unpack("<H", data[-2:])[0]:
            error_msg = "Unable to parse packet - incorrect CRC16: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        if crc8(data[:4]) != data[4]:
            error_msg = "Unable to parse packet - incorrect header CRC8: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        if payload_length < 8:
            error_msg = "Unable to parse packet - V4 payload too short: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        # Outer header fields - bytes [5:7] are not obfuscated
        type_byte = data[5]
        enc_type = (type_byte >> 5) & 0x7
        check_type = (type_byte >> 2) & 0x7
        is_rw_cmd = bool((type_byte >> 1) & 0x1)
        is_ack = bool(type_byte & 0x1)
        v4_type_a = data[6]
        v4_type_b = data[7]

        # Layer-2 deobfuscate - XOR bytes [8:8+payload_length] with the CRC8 key
        xor_key = data[4]
        inner_and_payload = bytes(b ^ xor_key for b in data[8 : 8 + payload_length])

        # Inner command header occupies the first 8 bytes of the deobfuscated block
        cmd_flags = inner_and_payload[0]
        frame_type = inner_and_payload[1]
        payload_type_val = inner_and_payload[2]
        time_snap_b0 = inner_and_payload[3]
        src = inner_and_payload[4]
        dst = inner_and_payload[5]
        cmd_set = inner_and_payload[6]
        cmd_id = inner_and_payload[7]

        actual_payload_len = payload_length - 8
        if actual_payload_len > 0:
            payload = inner_and_payload[8 : 8 + actual_payload_len]
            # Layer-3 deobfuscation - when v4_type_b is non-zero the device XOR-encodes
            # the application payload with it before encryption
            if v4_type_b:
                payload = bytes(b ^ v4_type_b for b in payload)
        else:
            payload = b""

        return PacketV4(
            src=src,
            dst=dst,
            cmd_set=cmd_set,
            cmd_id=cmd_id,
            payload=payload,
            enc_type=enc_type,
            check_type=check_type,
            is_rw_cmd=is_rw_cmd,
            is_ack=is_ack,
            frame_type=frame_type,
            payload_type=payload_type_val,
            cmd_flags=cmd_flags,
            v4_type_a=v4_type_a,
            v4_type_b=v4_type_b,
            time_snap_b0=time_snap_b0,
        )

    def to_bytes(self) -> bytes:
        inner_cmd = bytes(
            [
                self.cmd_flags,
                self.frame_type,
                self.payload_type,
                self.time_snap_b0,
                self.src,
                self.dst,
                self.cmd_set,
                self.cmd_id,
            ]
        )

        payload_length = 8 + len(self.payload)

        type_byte = (
            ((self.enc_type & 0x7) << 5)
            | ((self.check_type & 0x7) << 2)
            | (int(self.is_rw_cmd) << 1)
            | int(self.is_ack)
        )

        # Build outer header; CRC8 byte is also the XOR key for the inner content
        data = PacketV4.PREFIX
        data += struct.pack("<B", self.VERSION) + struct.pack("<H", payload_length)
        crc8_byte = crc8(data)
        data += struct.pack("<B", crc8_byte)
        data += struct.pack("<B", type_byte)
        data += struct.pack("<B", self.v4_type_a) + struct.pack("<B", self.v4_type_b)

        if self.v4_type_b:
            payload = bytes(b ^ self.v4_type_b for b in self.payload)
        else:
            payload = self.payload
        inner_content = inner_cmd + payload
        data += bytes(b ^ crc8_byte for b in inner_content)

        data += struct.pack("<H", crc16(data))

        return data

    def __repr__(self) -> str:
        return (
            "PacketV4("
            f"src=0x{self.src:02X}, "
            f"dst=0x{self.dst:02X}, "
            f"cmd_set=0x{self.cmd_set:02X}, "
            f"cmd_id=0x{self.cmd_id:02X}, "
            f"payload=bytes.fromhex('{self.payload_hex}'), "
            f"enc_type={self.enc_type}, "
            f"check_type={self.check_type}, "
            f"is_rw_cmd={self.is_rw_cmd}, "
            f"is_ack={self.is_ack}, "
            f"frame_type=0x{self.frame_type:02X}, "
            f"payload_type=0x{self.payload_type:02X}, "
            f"cmd_flags=0x{self.cmd_flags:02X}, "
            f"v4_type_a=0x{self.v4_type_a:02X}, "
            f"v4_type_b=0x{self.v4_type_b:02X}, "
            f"time_snap_b0=0x{self.time_snap_b0:02X}"
            ")"
        )


class InvalidPacket(Packet):
    """Represents an invalid packet that could not be parsed."""

    __slots__ = ("error_message",)

    def __init__(self, error_message: str):
        Packet.__init__(self, src=0, dst=0, cmd_set=0, cmd_id=0)
        self.error_message = error_message

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"InvalidPacket(error_message='{self.error_message}')"

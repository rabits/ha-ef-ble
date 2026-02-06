import logging
import struct
from typing import TypeGuard

from .crc import crc8, crc16

_LOGGER = logging.getLogger(__name__)


class Packet:
    """Needed to parse and make the internal packet structure"""

    PREFIX = b"\xaa"

    NET_BLE_COMMAND_CMD_CHECK_RET_TIME = 0x53
    NET_BLE_COMMAND_CMD_SET_RET_TIME = 0x52

    def __init__(
        self,
        src,
        dst,
        cmd_set,
        cmd_id,
        payload=b"",
        dsrc=1,
        ddst=1,
        version=3,
        seq=None,
        product_id=0,
    ):
        self._src = src
        self._dst = dst
        self._cmd_set = cmd_set
        self._cmd_id = cmd_id
        self._payload = payload
        self._dsrc = dsrc
        self._ddst = ddst
        self._version = version
        self._seq = seq if seq is not None else b"\x00\x00\x00\x00"
        self._product_id = product_id

        # For representation
        self._payload_hex = bytearray(self._payload).hex()

    @property
    def src(self):
        return self._src

    @property
    def dst(self):
        return self._dst

    @property
    def cmdSet(self):
        return self._cmd_set

    @property
    def cmdId(self):
        return self._cmd_id

    @property
    def payload(self):
        return self._payload

    @property
    def payloadHex(self):
        return self._payload_hex

    @property
    def dsrc(self):
        return self._dsrc

    @property
    def ddst(self):
        return self._ddst

    @property
    def version(self):
        return self._version

    @property
    def seq(self):
        return self._seq

    @property
    def productId(self):
        return self._product_id

    @staticmethod
    def fromBytes(data: bytes):
        """Deserializes bytes stream into internal data"""
        if not data.startswith(Packet.PREFIX):
            error_msg = "Unable to parse packet - prefix is incorrect: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        version = data[1]
        if (version == 2 and len(data) < 18) or (version in [3, 4] and len(data) < 20):
            error_msg = "Unable to parse packet - too small: %s"
            _LOGGER.error(error_msg, bytearray(data).hex())
            return InvalidPacket(error_msg % bytearray(data).hex())

        payload_length = struct.unpack("<H", data[2:4])[0]

        # there are also version 19 packets that do not contain crc16 checksum
        if version in [2, 3, 4]:
            # Check whole packet CRC16
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
        # data[10:12] # static zeroes?
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

            if version == 0x13:
                # If first byte of seq is set - we need to xor payload with it to get
                # the real data
                if seq[0] != b"\x00":
                    payload = bytes([c ^ seq[0] for c in payload])

                if payload[-2:] == b"\xbb\xbb":
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

    def toBytes(self):
        """Will serialize the internal data to bytes stream"""
        # Header
        data = Packet.PREFIX
        data += struct.pack("<B", self._version) + struct.pack("<H", len(self._payload))
        # Header crc
        data += struct.pack("<B", crc8(data))
        # Additional data
        data += self.productByte() + self._seq
        data += b"\x00\x00"  # Unknown static zeroes, no strings attached right now

        data += struct.pack("<B", self._src) + struct.pack("<B", self._dst)

        # V3+ includes dsrc/ddst fields, V2 does not
        if self._version >= 0x03:
            data += struct.pack("<B", self._dsrc) + struct.pack("<B", self._ddst)

        data += struct.pack("<B", self._cmd_set) + struct.pack("<B", self._cmd_id)
        # Payload
        data += self._payload
        # Packet crc
        data += struct.pack("<H", crc16(data))

        return data

    def productByte(self):
        """Return magics depends on product id"""

        if self._product_id >= 0:
            return b"\x0d"
        return b"\x0c"

    def __repr__(self):
        return (
            "Packet("
            f"src=0x{self._src:02X}, "
            f"dst=0x{self._dst:02X}, "
            f"cmd_set=0x{self._cmd_set:02X}, "
            f"cmd_id=0x{self._cmd_id:02X}, "
            f"payload=bytes.fromhex('{self._payload_hex}'), "
            f"dsrc=0x{self._dsrc:02X}, "
            f"ddst=0x{self._ddst:02X}, "
            f"version=0x{self._version:02X}, "
            f"seq={self._seq}, "
            f"product_id=0x{self._product_id:02X}"
            ")"
        )

    @staticmethod
    def is_invalid(packet: "Packet") -> TypeGuard["InvalidPacket"]:
        """Check if the given packet is invalid"""
        return isinstance(packet, InvalidPacket)


class InvalidPacket(Packet):
    """Represents an invalid packet that could not be parsed"""

    def __init__(self, error_message: str):
        super().__init__(src=0, dst=0, cmd_set=0, cmd_id=0, payload=b"")
        self.error_message = error_message

    def __bool__(self):
        return False

    def __repr__(self):
        return f"InvalidPacket(error_message='{self.error_message}')"

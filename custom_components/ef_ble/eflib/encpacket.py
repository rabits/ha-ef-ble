import struct

from .crc import crc16
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

class EncPacket:
    """Outside wrapper of Packet that actually transferred through the BLE channel"""
    PREFIX = b'\x5A\x5A'

    FRAME_TYPE_COMMAND = 0x00
    FRAME_TYPE_PROTOCOL = 0x01
    FRAME_TYPE_PROTOCOL_INT = 0x10

    PAYLOAD_TYPE_VX_PROTOCOL = 0x00
    PAYLOAD_TYPE_ODM_PROTOCOL = 0x04

    def __init__(self, frame_type, payload_type, payload, cmd_id = 0, version = 0, seq = 0, enc_key = None, iv = None):
        self._frame_type   = frame_type
        self._payload_type = payload_type
        self._payload      = payload
        self._cmd_id       = cmd_id
        self._version      = version
        self._seq          = seq
        self._enc_key      = enc_key
        self._iv           = iv

    def encryptPayload(self):
        if self._enc_key == None and self._iv == None:
            return self._payload # Not encrypted

        engine = AES.new(self._enc_key, AES.MODE_CBC, self._iv)
        return engine.encrypt(pad(self._payload, AES.block_size))

    def toBytes(self):
        '''Will serialize the internal data to bytes stream'''
        payload = self.encryptPayload()

        data = EncPacket.PREFIX + struct.pack('<B', self._frame_type << 4) + b'\x01'  # Unknown byte
        data += struct.pack('<H', len(payload)+2)  # +2 here is len(crc16)
        data += payload
        data += struct.pack('<H', crc16(data))

        return data

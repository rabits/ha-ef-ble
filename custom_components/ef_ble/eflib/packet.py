import struct

from .crc import crc16, crc8

class Packet:
    """Needed to parse and make the internal packet structure"""
    PREFIX = b'\xAA'

    def __init__(self, src, dst, cmd_set, cmd_id, payload = b'', dsrc = 1, ddst = 1, version = 3, seq = 0, product_id = 0):
        self._src        = src
        self._dst        = dst
        self._cmd_set    = cmd_set
        self._cmd_id     = cmd_id
        self._payload    = payload
        self._dsrc       = dsrc
        self._ddst       = ddst
        self._version    = version
        self._seq        = seq
        self._product_id = product_id

    def payload(self):
        return self._payload

    def cmdSet(self):
        return self._cmd_set

    def cmdId(self):
        return self._cmd_id

    def src(self):
        return self._src

    @staticmethod
    def fromBytes(data):
        '''Deserializes bytes stream into internal data'''
        if len(data) < 20:
            print("ERROR: Unable to parse packet - too small: " + " ".join("{:02x}".format(c) for c in data))
            return None

        if not data.startswith(Packet.PREFIX):
            print("ERROR: Unable to parse packet - prefix is incorrect: " + " ".join("{:02x}".format(c) for c in data))
            return None

        version = data[1]
        payload_length = struct.unpack('<H', data[2:4])[0]

        if version == 3:
            # Check whole packet CRC16
            if crc16(data[:-2]) != struct.unpack('<H', data[-2:])[0]:
                print("ERROR: Unable to parse packet - incorrect CRC16: " + " ".join("{:02x}".format(c) for c in data))
                return None

        # Check header CRC8
        if crc8(data[:4]) != data[4]:
            print("ERROR: Unable to parse packet - incorrect header CRC8: " + " ".join("{:02x}".format(c) for c in data))
            return None

        #data[4] # crc8 of header
        #product_id = data[5] # We can't determine the product id from the bytestream

        seq = struct.unpack('<L', data[6:10])[0]
        # data[10:12] # static zeroes?
        src = data[12]
        dst = data[13]
        dsrc = data[14]
        ddst = data[15]
        cmd_set = data[16]
        cmd_id = data[17]

        payload = b''
        if payload_length > 0:
            payload = data[18:18+payload_length]

        if version == 19 and payload[-2:] == b'\xbb\xbb':
            payload = payload[:-2]

        return Packet(src, dst, cmd_set, cmd_id, payload, dsrc, ddst, version, seq)

    def toBytes(self):
        '''Will serialize the internal data to bytes stream'''
        # Header
        data = Packet.PREFIX
        data += struct.pack('<B', self._version) + struct.pack('<H', len(self._payload))
        # Header crc
        data += struct.pack('<B', crc8(data))
        # Additional data
        data += self.productByte() + struct.pack('<L', self._seq)
        data += b'\x00\x00' # Unknown static zeroes, no strings attached right now
        data += struct.pack('<B', self._src) + struct.pack('<B', self._dst)
        data += struct.pack('<B', self._dsrc) + struct.pack('<B', self._ddst)
        data += struct.pack('<B', self._cmd_set) + struct.pack('<B', self._cmd_id)
        # Payload
        data += self._payload
        # Packet crc
        data += struct.pack('<H', crc16(data))

        return data

    def productByte(self):
        '''Returns magics depends on product id'''
        if self._product_id >= 0:
            return b'\x0d'
        else:
            return b'\x0c'

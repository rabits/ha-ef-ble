from ..devicebase import DeviceBase
from ..model.kt210_sac import KT210SAC
from ..packet import Packet
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

pb = dataclass_attr_mapper(KT210SAC)


class Device(DeviceBase, RawDataProps):
    """Wave 2"""

    SN_PREFIX = b"KT21"
    NAME_PREFIX = "EF-KT2"

    @property
    def packet_version(self):
        return 2

    battery_level = raw_field(pb.bat_soc)

    battery_power = raw_field(pb.bat_pwr_watt)

    ambient_temperature = raw_field(pb.env_temp, lambda v: round(v, 2))
    outlet_temperature = raw_field(pb.outlet_temp)
    mode = raw_field(pb.mode)

    @classmethod
    def check(cls, sn):
        return sn.startswith(cls.SN_PREFIX)

    async def packet_parse(self, data: bytes) -> Packet:
        # Wave 2 uses V2 protocol with XOR encoding based on sequence number
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        self.reset_updated()
        if packet.src == 0x42 and packet.cmdSet == 0x42 and packet.cmdId == 0x50:
            self.update_from_bytes(KT210SAC, packet.payload)
            processed = True
        # elif packet.src == 0x06 and packet.cmdSet == 0x20 and packet.cmdId == 0x32:
        #     self.update_from_bytes(WaveInfo, packet.payload)
        #     processed = False

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

from ..devicebase import DeviceBase
from ..model.pd_heart import BasePdHeart
from ..packet import Packet
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

pb = dataclass_attr_mapper(BasePdHeart)


class Device(DeviceBase, RawDataProps):
    """Delta 2"""

    SN_PREFIX = (b"R331", b"R335", b"D361")
    NAME_PREFIX = "EF-R33"

    @property
    def packet_version(self):
        return 2

    ac_input_power = raw_field(pb.ac_chg_power)
    ac_output_power = raw_field(pb.ac_dsg_power)

    battery_level = raw_field(pb.soc)
    input_power = raw_field(pb.watts_in_sum)
    output_power = raw_field(pb.watts_out_sum)

    usbc_output_power = raw_field(pb.typec1_watts)
    usba_output_power = raw_field(pb.usb1_watt)
    usba2_output_power = raw_field(pb.usb2_watt)

    cell_temperature = raw_field(pb.car_temp)

    dc_port_input_power = raw_field(pb.dc_chg_power)
    dc12v_output_power = raw_field(pb.dc_dsg_power)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self):
        model = "2"
        match self._sn[:4]:
            case "D361":
                model = "3 1500"

        return f"Delta {model}"

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet) -> bool:
        """Process the incoming notifications from the device"""

        processed = False
        self.reset_updated()

        if packet.src == 0x02 and packet.cmdSet == 0x20 and packet.cmdId == 0x02:
            self.update_from_data(BasePdHeart.from_bytes(packet.payload))
            processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

"""EcoFlow PowerPulse EV charger (CP307 protocol)."""

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import cp307_iot_pb2
from ..props import ProtobufProps, pb_field, proto_attr_mapper
from ..props.enums import IntFieldValue
from ..props.utils import pround

pb = proto_attr_mapper(cp307_iot_pb2.HeartBeat)


class AcPlugState(IntFieldValue):
    UNKNOWN = -1
    UNPLUGGED = 1
    PLUGGED_IN = 2
    CHARGING = 3
    PAUSED = 4
    CHARGE_COMPLETE = 6
    STANDBY = 7
    UPDATING = 8


class Device(DeviceBase, ProtobufProps):
    """PowerPulse"""

    SN_PREFIX = (
        b"C101",  # PowerPulse 9.6 kW DIY
        b"C102",  # PowerPulse 11.5 kW
        b"C103",  # PowerPulse 9.6 kW
        b"C371",  # PowerPulse 7 kW
        b"C372",  # PowerPulse 22 kW
        b"C373",  # PowerPulse 22 kW Pro
        b"C374",  # PowerPulse 22 kW Meter
        b"C375",  # PowerPulse 11 kW
        b"C376",  # PowerPulse 11 kW Meter
    )
    NAME_PREFIX = "EF-C10"

    ac_plug_state = pb_field(pb.system_state, AcPlugState.from_value)
    output_power = pb_field(pb.charge_power, pround(1))
    ac_output_voltage = pb_field(pb.mid_meter.volt_l1, pround(1))
    ac_output_current = pb_field(pb.mid_meter.curr_l1, pround(2))
    total_energy = pb_field(pb.energy_value)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self) -> str:
        match self._sn[:4]:
            case "C102":
                model = "11.5 kW"
            case "C103":
                model = "9.6 kW"
            case "C371":
                model = "7 kW"
            case "C372":
                model = "22 kW"
            case "C373":
                model = "22 kW Pro"
            case "C374":
                model = "22 kW Meter"
            case "C375":
                model = "11 kW"
            case "C376":
                model = "11 kW Meter"
            case _:
                model = "9.6 kW DIY"
        return f"PowerPulse EV Charger ({model})"

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        self.reset_updated()

        match packet.src, packet.cmdSet, packet.cmdId:
            case (0x02, 0x02, 0x21):
                self.update_from_bytes(cp307_iot_pb2.HeartBeat, packet.payload)
                processed = True
            case (0x35, 0x01, Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME):
                if len(packet.payload) == 0:
                    self._time_commands.async_send_all()
                processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

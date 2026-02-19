from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import (
    iot_comm_pb2,
    jt_s1_ecology_dev_pb2,
    jt_s1_sys_pb2,
    platform_comm_pb2,
)
from ..props import (
    ProtobufProps,
    pb_field,
    proto_attr_mapper,
)

pb_heartbeat = proto_attr_mapper(jt_s1_sys_pb2.HeartbeatReport)
pb_moduleinfo = proto_attr_mapper(iot_comm_pb2.ModuleInfo)


class Device(DeviceBase, ProtobufProps):
    SN_PREFIX = (b"J32",)
    NAME_PREFIX = "EF-J32"

    grid_power = pb_field(pb_heartbeat.ems_bp_power)

    @classmethod
    def check(cls, sn: bytes):
        return sn[:3] in cls.SN_PREFIX

    async def packet_parse(self, data: bytes):
        return Packet.from_bytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet):
        processed = True
        self.reset_updated()

        match packet.src, packet.cmd_set, packet.cmd_id:
            case _, 0xFE, 0x10:
                self.update_from_bytes(
                    platform_comm_pb2.EventRecordReport, packet.payload
                )
                # TODO(gnox): should respond with platform_comm_pb2.EventInfoReportAck
            case 0x35, 0x35, 0x71:
                self.update_from_bytes(iot_comm_pb2.ModuleClusterInfo, packet.payload)
            case 0x60, 0x60, 0x01:
                self.update_from_bytes(jt_s1_sys_pb2.HeartbeatReport, packet.payload)
            case 0x60, 0x60, 0x03:
                self.update_from_bytes(jt_s1_sys_pb2.ErrorChangeReport, packet.payload)
            case 0x60, 0x60, 0x07:
                self.update_from_bytes(jt_s1_sys_pb2.BpHeartbeatReport, packet.payload)
            case 0x60, 0x60, 0x08:
                self.update_from_bytes(jt_s1_sys_pb2.EmsChangeReport, packet.payload)
            case 0x60, 0x60, 0x0D:
                # NOTE(gnox): network config data - even though it is parsable as
                # protocol buffers, in the app, it's parsed manually into NetConfig
                # beans
                pass
            case 0x60, 0x60, 0x0A:
                self.update_from_bytes(
                    jt_s1_sys_pb2.EmsAllTimerTaskReport, packet.payload
                )
            case 0x60, 0x60, 0x0B:
                self.update_from_bytes(
                    jt_s1_sys_pb2.EmsEcologyDevReport, packet.payload
                )
            case 0x60, 0x60, 0x21:
                self.update_from_bytes(jt_s1_sys_pb2.EnergyStreamReport, packet.payload)
            case 0x60, 0xE0, 0x01:
                self.update_from_bytes(
                    jt_s1_ecology_dev_pb2.EcologyDevGetAck, packet.payload
                )
            case _:
                processed = False

        self._notify_updated()

        return processed

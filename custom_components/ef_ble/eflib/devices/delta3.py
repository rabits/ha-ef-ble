from ..pb import pd335_sys_pb2
from ..props import pb_field
from . import delta3_classic

pb = delta3_classic.pb


class Device(delta3_classic.Device):
    """Delta 3"""

    SN_PREFIX = (b"P231",)
    NAME_PREFIX = "EF-D3"

    usb_ports = pb_field(pb.flow_info_qcusb1, delta3_classic._flow_is_on)

    async def enable_usb_ports(self, enabled: bool):
        await self._send_config_packet(pd335_sys_pb2.ConfigWrite(cfg_usb_open=enabled))

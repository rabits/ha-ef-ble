from ..device_options import UNLOCK_AC_CHARGING_MINIMUM, option_field
from ..entity import controls
from ..pb import pd335_sys_pb2
from ..props import pb_field
from ..props.transforms import flow_is_on
from . import delta3_classic

pb = delta3_classic.pb


class Device(delta3_classic.Device):
    """Delta 3"""

    SN_PREFIX = (b"P231",)
    NAME_PREFIX = "EF-D3"

    ac_charging_speed_min = option_field(
        UNLOCK_AC_CHARGING_MINIMUM, enabled=1, disabled=100
    )

    usb_ports = pb_field(pb.flow_info_qcusb1, flow_is_on)

    @controls.switch(usb_ports)
    async def enable_usb_ports(self, enabled: bool):
        await self._send_config_packet(pd335_sys_pb2.ConfigWrite(cfg_usb_open=enabled))

from ..pb import pd335_sys_pb2
from ..props import pb_field
from . import _delta3_base, delta3_classic

pb = delta3_classic.pb


class Device(delta3_classic.Device):
    """Delta 3"""

    SN_PREFIX = (b"P231",)
    NAME_PREFIX = "EF-D3"

    usb_ports = pb_field(pb.flow_info_qcusb1, _delta3_base.flow_is_on)

    # Energy strategy operation modes
    energy_strategy_self_powered = pb_field(
        pb.energy_strategy_operate_mode,
        lambda x: x.operate_self_powered_open if x else None,
    )
    energy_strategy_scheduled = pb_field(
        pb.energy_strategy_operate_mode,
        lambda x: x.operate_scheduled_open if x else None,
    )
    energy_strategy_tou = pb_field(
        pb.energy_strategy_operate_mode,
        lambda x: x.operate_tou_mode_open if x else None,
    )

    async def enable_usb_ports(self, enabled: bool):
        await self._send_config_packet(pd335_sys_pb2.ConfigWrite(cfg_usb_open=enabled))

    async def enable_energy_strategy_self_powered(self, enabled: bool):
        config = pd335_sys_pb2.ConfigWrite()
        config.cfg_energy_strategy_operate_mode.operate_self_powered_open = enabled
        await self._send_config_packet(config)

    async def enable_energy_strategy_scheduled(self, enabled: bool):
        config = pd335_sys_pb2.ConfigWrite()
        config.cfg_energy_strategy_operate_mode.operate_scheduled_open = enabled
        await self._send_config_packet(config)

    async def enable_energy_strategy_tou(self, enabled: bool):
        config = pd335_sys_pb2.ConfigWrite()
        config.cfg_energy_strategy_operate_mode.operate_tou_mode_open = enabled
        await self._send_config_packet(config)

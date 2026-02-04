from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..pb import pd335_sys_pb2
from ..props import pb_field
from ._delta3_base import Delta3Base, _out_power, pb


class Device(Delta3Base):
    """Delta 3 Classic"""

    SN_PREFIX = (b"P321",)
    NAME_PREFIX = "EF-P3"

    dc12v_output_power = pb_field(pb.pow_get_12v, _out_power)
    disable_grid_bypass = pb_field(pb.bypass_out_disable)

    # NOTE(gnox): self_powered is the same thing as energy_backup, should we remove it?
    # also, shouldn't this be a single select instead of 3 switches?
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

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)
        self.max_ac_charging_power = 1500

    def _after_message_parsed(self):
        pass

    async def enable_disable_grid_bypass(self, enabled: bool):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_bypass_out_disable=enabled)
        )

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

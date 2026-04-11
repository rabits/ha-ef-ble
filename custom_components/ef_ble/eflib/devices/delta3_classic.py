from ..entity import controls
from ..entity.base import dynamic
from ..pb import pd335_sys_pb2
from ..props import pb_field
from ._delta3_base import Delta3Base, flow_is_on, out_power, pb


class Device(Delta3Base):
    """Delta 3 Classic"""

    SN_PREFIX = (b"P321",)
    NAME_PREFIX = "EF-P3"

    energy_backup = pb_field(pb.energy_backup_en)
    energy_backup_battery_level = pb_field(pb.energy_backup_start_soc)

    dc_12v_port = pb_field(pb.flow_info_12v, flow_is_on)
    dc12v_output_power = pb_field(pb.pow_get_12v, out_power)
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

    @controls.switch(disable_grid_bypass, enabled=False)
    async def enable_disable_grid_bypass(self, enabled: bool):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_bypass_out_disable=enabled)
        )

    @controls.switch(energy_strategy_self_powered)
    async def enable_energy_strategy_self_powered(self, enabled: bool):
        config = pd335_sys_pb2.ConfigWrite()
        config.cfg_energy_strategy_operate_mode.operate_self_powered_open = enabled
        await self._send_config_packet(config)

    @controls.switch(energy_strategy_scheduled)
    async def enable_energy_strategy_scheduled(self, enabled: bool):
        config = pd335_sys_pb2.ConfigWrite()
        config.cfg_energy_strategy_operate_mode.operate_scheduled_open = enabled
        await self._send_config_packet(config)

    @controls.switch(energy_strategy_tou)
    async def enable_energy_strategy_tou(self, enabled: bool):
        config = pd335_sys_pb2.ConfigWrite()
        config.cfg_energy_strategy_operate_mode.operate_tou_mode_open = enabled
        await self._send_config_packet(config)

    @controls.switch(energy_backup)
    async def enable_energy_backup(self, enabled: bool):
        config = pd335_sys_pb2.ConfigWrite()
        config.cfg_energy_backup.energy_backup_en = enabled
        if enabled and self.energy_backup_battery_level is not None:
            config.cfg_energy_backup.energy_backup_start_soc = (
                self.energy_backup_battery_level or 50
            )
        await self._send_config_packet(config)

    @controls.battery(
        energy_backup_battery_level,
        min=dynamic(Delta3Base.battery_charge_limit_min),
        max=dynamic(Delta3Base.battery_charge_limit_max),
        availability=dynamic(energy_backup),
    )
    async def set_energy_backup_battery_level(self, value: float):
        config = pd335_sys_pb2.ConfigWrite()
        config.cfg_energy_backup.energy_backup_en = True
        config.cfg_energy_backup.energy_backup_start_soc = int(value)
        await self._send_config_packet(config)
        return True

    @controls.switch(dc_12v_port)
    async def enable_dc_12v_port(self, enabled: bool):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_dc_12v_out_open=enabled)
        )

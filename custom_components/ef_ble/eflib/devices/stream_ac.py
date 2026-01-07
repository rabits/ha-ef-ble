import time
from collections.abc import Sequence

from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import bk_series_pb2
from ..props import (
    Field,
    ProtobufProps,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)
from ..props.enums import IntFieldValue
from ..props.protobuf_field import proto_has_attr

pb = proto_attr_mapper(bk_series_pb2.DisplayPropertyUpload)
pb_time_task = proto_attr_mapper(bk_series_pb2.TimerTask)


def _round(value: float):
    return round(value, 2)


class ResidentLoad(repeated_pb_field_type(pb.day_resident_load_list.load)):
    def get_item(
        self, value: Sequence[bk_series_pb2.ResidentLoad]
    ) -> bk_series_pb2.ResidentLoad | None:
        return value[0] if len(value) == 1 else None


class ChargingTimerTask(repeated_pb_field_type(pb.all_timer_task.time_task)):
    def get_item(
        self, value: Sequence[bk_series_pb2.TimerTask]
    ) -> bk_series_pb2.TimerTask | None:
        if not value:
            return None

        for task in value:
            if (
                proto_has_attr(task, pb_time_task.chg_task)
                and len(task.chg_task.dev_target_soc) == 1
            ):
                return task

        return None


class EnergyStrategy(IntFieldValue):
    SELF_POWERED = 1
    SCHEDULED = 2
    TOU = 3
    INTELLIGENT_SCHEDULE = 4

    UNKNOWN = -1

    @classmethod
    def from_pb(cls, strategy: bk_series_pb2.CfgEnergyStrategyOperateMode):
        if strategy.operate_self_powered_open:
            return cls.SELF_POWERED

        if strategy.operate_scheduled_open:
            return cls.SCHEDULED

        if strategy.operate_tou_mode_open:
            return cls.TOU

        if strategy.operate_intelligent_schedule_mode_open:
            return cls.INTELLIGENT_SCHEDULE
        return cls.UNKNOWN

    def as_pb(
        self, operate_mode: bk_series_pb2.CfgEnergyStrategyOperateMode | None = None
    ):
        if operate_mode is None:
            operate_mode = bk_series_pb2.CfgEnergyStrategyOperateMode()
        else:
            operate_mode.operate_self_powered_open = False
            operate_mode.operate_scheduled_open = False
            operate_mode.operate_intelligent_schedule_mode_open = False
            operate_mode.operate_tou_mode_open = False

        match self:
            case EnergyStrategy.SELF_POWERED:
                operate_mode.operate_self_powered_open = True
            case EnergyStrategy.SCHEDULED:
                operate_mode.operate_scheduled_open = True
            case EnergyStrategy.TOU:
                operate_mode.operate_tou_mode_open = True
            case EnergyStrategy.INTELLIGENT_SCHEDULE:
                operate_mode.operate_intelligent_schedule_mode_open = True
        return operate_mode


class Device(DeviceBase, ProtobufProps):
    """STREAM AC"""

    SN_PREFIX = (b"BK51",)
    NAME_PREFIX = "EF-6"

    battery_level = pb_field(pb.cms_batt_soc)
    battery_level_main = pb_field(pb.bms_batt_soc)
    cell_temperature = pb_field(pb.bms_max_cell_temp)

    grid_power = pb_field(pb.grid_connection_power)
    grid_voltage = pb_field(pb.grid_connection_vol, _round)
    grid_frequency = pb_field(pb.grid_connection_freq, _round)

    battery_charge_limit_min = pb_field(pb.cms_min_dsg_soc)
    battery_charge_limit_max = pb_field(pb.cms_max_chg_soc)

    load_from_battery = pb_field(pb.pow_get_sys_load_from_bp, _round)
    load_from_grid = pb_field(pb.pow_get_sys_load_from_grid, _round)

    feed_grid = pb_field(pb.feed_grid_mode, lambda x: x == 2)
    feed_grid_pow_limit = pb_field(pb.feed_grid_mode_pow_limit)
    feed_grid_pow_max = pb_field(pb.feed_grid_mode_pow_max)

    energy_strategy = pb_field(
        pb.energy_strategy_operate_mode,
        EnergyStrategy.from_pb,
    )
    energy_backup_battery_level = pb_field(pb.backup_reverse_soc)

    grid_in_power_limit = pb_field(pb.sys_grid_in_pwr_limit)
    max_ac_in_power = pb_field(pb.pow_sys_ac_in_max)

    _resident_load = ResidentLoad()
    load_power_enabled = Field[bool]()
    base_load_power = Field[int]()

    _charging_task = ChargingTimerTask()
    _all_timer_tasks = pb_field(pb.all_timer_task)
    charging_grid_power_limit_enabled = Field[bool]()
    charging_grid_power_limit = Field[int]()
    max_bp_input = pb_field(pb.max_bp_input)

    @property
    def _charging_grid_power_limit(self):
        if self._charging_task is None:
            return None
        dev_target_soc = self._charging_task.chg_task.dev_target_soc

        return dev_target_soc[0].chg_from_grid_power_limited

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet):
        processed = False
        self.reset_updated()

        if packet.src == 0x02 and packet.cmdSet == 0xFE and packet.cmdId == 0x15:
            self.update_from_bytes(bk_series_pb2.DisplayPropertyUpload, packet.payload)
            processed = True

        self.load_power_enabled = self._resident_load is not None
        if self._resident_load is not None:
            self.base_load_power = self._resident_load.load_power

        self.charging_grid_power_limit_enabled = (
            self._charging_grid_power_limit is not None
        )

        if (power_limit := self._charging_grid_power_limit) is not None:
            self.charging_grid_power_limit = power_limit

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def _send_config_packet(self, message: bk_series_pb2.ConfigWrite):
        payload = message.SerializeToString()
        message.cfg_utc_time = round(time.time())
        packet = Packet(0x20, 0x02, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

    async def set_battery_charge_limit_max(self, limit: int):
        await self._send_config_packet(bk_series_pb2.ConfigWrite(cfg_max_chg_soc=limit))
        return True

    async def set_battery_charge_limit_min(self, limit: int):
        await self._send_config_packet(bk_series_pb2.ConfigWrite(cfg_min_dsg_soc=limit))
        return True

    async def enable_ac_1(self, enable: bool):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_relay2_onoff=enable)
        )

    async def enable_ac_2(self, enable: bool):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_relay3_onoff=enable)
        )

    async def set_energy_backup_battery_level(self, value: int):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_backup_reverse_soc=value)
        )
        return True

    async def set_feed_grid_pow_limit(self, value: int):
        if self.feed_grid_pow_max is None or value > self.feed_grid_pow_max:
            return False
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_feed_grid_mode_pow_limit=value)
        )
        return True

    async def enable_feed_grid(self, enable: bool):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_feed_grid_mode=2 if enable else 1)
        )

    async def set_energy_strategy(self, strategy: EnergyStrategy):
        cfg = bk_series_pb2.ConfigWrite()
        strategy.as_pb(cfg.cfg_energy_strategy_operate_mode)
        await self._send_config_packet(cfg)

    async def set_load_power(self, limit: int):
        if self._resident_load is None:
            return False

        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(
                cfg_day_resident_load_list=bk_series_pb2.DayResidentLoadList(
                    load=[
                        bk_series_pb2.ResidentLoad(
                            load_power=limit,
                            start_min=self._resident_load.start_min,
                            end_min=self._resident_load.end_min,
                        )
                    ]
                )
            )
        )
        return True

    async def set_grid_in_pow_limit(self, value: int):
        if self.max_ac_in_power is None or value > self.max_ac_in_power or value < 0:
            return False

        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_sys_grid_in_pwr_limit=value)
        )
        return True

    async def set_charging_grid_power_limit(self, limit: int):
        if (
            self._charging_task is None
            or self._all_timer_tasks is None
            or len(self._charging_task.chg_task.dev_target_soc) != 1
        ):
            return False

        config = bk_series_pb2.ConfigWrite()

        for task in self._all_timer_tasks.time_task:
            new_task = config.cfg_all_timer_task.time_task.add()
            new_task.CopyFrom(task)

            if task.task_index == self._charging_task.task_index:
                new_task.chg_task.dev_target_soc[0].chg_from_grid_power_limited = limit

        await self._send_config_packet(config)
        return True

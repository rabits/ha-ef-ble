import asyncio
import dataclasses
import time
from collections.abc import Callable, Sequence
from typing import ClassVar

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..devicebase import DeviceBase
from ..entity import controls
from ..entity.base import dynamic
from ..packet import Packet
from ..pb import bk_series_pb2
from ..props import (
    ProtobufProps,
    computed_field,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)
from ..props.enums import IntFieldValue
from ..props.protobuf_field import proto_has_attr
from ..props.transforms import pround

pb = proto_attr_mapper(bk_series_pb2.DisplayPropertyUpload)
pb_time_task = proto_attr_mapper(bk_series_pb2.TimerTask)


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
                and len(task.chg_task.dev_target_soc) > 0
            ):
                return task

        return None


class DischargingTimerTask(repeated_pb_field_type(pb.all_timer_task.time_task)):
    def get_item(
        self, value: Sequence[bk_series_pb2.TimerTask]
    ) -> bk_series_pb2.TimerTask | None:
        if not value:
            return None

        for task in value:
            if proto_has_attr(task, pb_time_task.home_need_power_limited):
                return task

        return None


@dataclasses.dataclass
class _TimerTaskChain:
    """
    Shared state for linked STREAM devices that send the same `all_timer_task` config

    Ensures concurrent commands from different devices in the chain don't overwrite each
    other.
    """

    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    pending_mods: list[tuple[int, Callable[[bk_series_pb2.TimerTask], None]]] = (
        dataclasses.field(default_factory=list)
    )


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

    _timer_task_chains: ClassVar[dict[frozenset[str], _TimerTaskChain]] = {}

    battery_level = pb_field(pb.cms_batt_soc)
    battery_level_main = pb_field(pb.bms_batt_soc)
    cell_temperature = pb_field(pb.bms_max_cell_temp)

    remaining_time_charging = pb_field(pb.cms_chg_rem_time)
    remaining_time_discharging = pb_field(pb.cms_dsg_rem_time)

    grid_power = pb_field(pb.grid_connection_power, pround(2))
    grid_voltage = pb_field(pb.grid_connection_vol, pround(2))
    grid_frequency = pb_field(pb.grid_connection_freq, pround(2))

    battery_charge_limit_min = pb_field(pb.cms_min_dsg_soc)
    battery_charge_limit_max = pb_field(pb.cms_max_chg_soc)

    battery_power = pb_field(pb.pow_get_bp_cms, pround(2))
    load_from_battery = pb_field(pb.pow_get_sys_load_from_bp, pround(2))
    load_from_grid = pb_field(pb.pow_get_sys_load_from_grid, pround(2))

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
    max_ac_out_power = pb_field(pb.pow_sys_ac_out_max)

    _resident_load = ResidentLoad()
    max_bp_input = pb_field(pb.max_bp_input)

    _charging_task = ChargingTimerTask()
    _discharging_task = DischargingTimerTask()
    _all_timer_tasks = pb_field(pb.all_timer_task)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._timer_task_chain: _TimerTaskChain | None = None

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    async def data_parse(self, packet: Packet):
        processed = False
        self.reset_updated()

        if packet.src == 0x02 and packet.cmdSet == 0xFE and packet.cmdId == 0x15:
            self.update_from_bytes(bk_series_pb2.DisplayPropertyUpload, packet.payload)
            processed = True

        self._notify_updated()

        return processed

    @computed_field
    def load_power_enabled(self) -> bool:
        return self._resident_load is not None

    @computed_field
    def base_load_power(self) -> int | None:
        if self._resident_load is None:
            return None
        return self._resident_load.load_power

    @computed_field
    def charging_grid_power_limit_enabled(self) -> bool:
        return self._dev_target_soc is not None

    @computed_field
    def charging_grid_power_limit(self) -> int | None:
        target = self._dev_target_soc
        return target.chg_from_grid_power_limited if target is not None else None

    @computed_field
    def charging_grid_target_soc(self) -> int | None:
        target = self._dev_target_soc
        return target.target_soc if target is not None else None

    @computed_field
    def charging_task_enabled(self) -> bool | None:
        if self._charging_task is None:
            return None
        return self._charging_task.is_enable

    @computed_field
    def discharging_task_available(self) -> bool:
        return self._discharging_task is not None

    @computed_field
    def discharging_task_enabled(self) -> bool | None:
        if self._discharging_task is None:
            return None
        return self._discharging_task.is_enable

    @computed_field
    def discharging_power_limit(self) -> int | None:
        if self._discharging_task is None:
            return None
        return self._discharging_task.home_need_power_limited

    @property
    def _dev_target_soc(self):
        if self._charging_task is None:
            return None

        for target_soc in self._charging_task.chg_task.dev_target_soc:
            if target_soc.sn == self._sn:
                return target_soc

        return None

    async def _send_config_packet(self, message: bk_series_pb2.ConfigWrite):
        message.cfg_utc_time = round(time.time())
        payload = message.SerializeToString()
        packet = Packet(0x20, 0x02, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

    @controls.battery(
        battery_charge_limit_max,
        min=dynamic(battery_charge_limit_min),
    )
    async def set_battery_charge_limit_max(self, limit: float):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_max_chg_soc=int(limit))
        )
        return True

    @controls.battery(
        battery_charge_limit_min,
        max=dynamic(battery_charge_limit_max),
    )
    async def set_battery_charge_limit_min(self, limit: float):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_min_dsg_soc=int(limit))
        )
        return True

    @controls.battery(
        energy_backup_battery_level,
        min=dynamic(battery_charge_limit_min),
        max=dynamic(battery_charge_limit_max),
    )
    async def set_energy_backup_battery_level(self, value: float):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_backup_reverse_soc=int(value))
        )
        return True

    @controls.power(feed_grid_pow_limit, max=dynamic(feed_grid_pow_max))
    async def set_feed_grid_pow_limit(self, value: float):
        if self.feed_grid_pow_max is None or value > self.feed_grid_pow_max:
            return False
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_feed_grid_mode_pow_limit=int(value))
        )
        return True

    @controls.switch(feed_grid)
    async def enable_feed_grid(self, enable: bool):
        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_feed_grid_mode=2 if enable else 1)
        )

    @controls.select(energy_strategy, options=EnergyStrategy)
    async def set_energy_strategy(self, strategy: EnergyStrategy):
        cfg = bk_series_pb2.ConfigWrite()
        strategy.as_pb(cfg.cfg_energy_strategy_operate_mode)
        await self._send_config_packet(cfg)

    @controls.power(
        base_load_power,
        max=dynamic(feed_grid_pow_max),
        availability=dynamic(load_power_enabled),
    )
    async def set_load_power(self, limit: float):
        if self._resident_load is None:
            return False

        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(
                cfg_day_resident_load_list=bk_series_pb2.DayResidentLoadList(
                    load=[
                        bk_series_pb2.ResidentLoad(
                            load_power=int(limit),
                            start_min=self._resident_load.start_min,
                            end_min=self._resident_load.end_min,
                        )
                    ]
                )
            )
        )
        return True

    @controls.power(grid_in_power_limit, max=dynamic(max_ac_in_power))
    async def set_grid_in_pow_limit(self, value: float):
        if self.max_ac_in_power is None or value > self.max_ac_in_power or value < 0:
            return False

        await self._send_config_packet(
            bk_series_pb2.ConfigWrite(cfg_sys_grid_in_pwr_limit=int(value))
        )
        return True

    @controls.power(
        charging_grid_power_limit,
        max=dynamic(max_bp_input),
        availability=dynamic(charging_grid_power_limit_enabled),
    )
    async def set_charging_grid_power_limit(self, limit: float):
        def set_power_limit(dev_soc: bk_series_pb2.DeviceTargetSoc):
            dev_soc.chg_from_grid_power_limited = int(limit)

        return await self._send_charging_task_packet(set_power_limit)

    @controls.battery(
        charging_grid_target_soc,
        max=100,
        availability=dynamic(charging_grid_power_limit_enabled),
    )
    async def set_charging_grid_target_soc(self, soc: float):
        def set_target_soc(dev_soc: bk_series_pb2.DeviceTargetSoc):
            dev_soc.target_soc = int(soc)

        return await self._send_charging_task_packet(set_target_soc)

    async def _send_timer_task_packet(
        self,
        target: bk_series_pb2.TimerTask | None,
        modify: Callable[[bk_series_pb2.TimerTask], None],
    ) -> bool:
        chain = self._get_chain()
        async with chain.lock:
            if target is None or self._all_timer_tasks is None:
                return False

            chain.pending_mods.append((target.task_index, modify))

            config = bk_series_pb2.ConfigWrite()

            for task in self._all_timer_tasks.time_task:
                new_task = config.cfg_all_timer_task.time_task.add()
                new_task.CopyFrom(task)

                for mod_idx, mod_fn in chain.pending_mods:
                    if task.task_index == mod_idx:
                        mod_fn(new_task)

            await self._send_config_packet(config)

            # Clear pending mods after the device has had time to process and send back
            # updated state
            self.call_later(
                5.0,
                chain.pending_mods.clear,
                key="pending_task_mods",
            )

            return True

    async def _send_charging_task_packet(
        self,
        modify_dev_target_soc: Callable[[bk_series_pb2.DeviceTargetSoc], None],
    ):
        if (
            self._charging_task is None
            or len(self._charging_task.chg_task.dev_target_soc) < 1
        ):
            return False

        sn = self._sn

        def modify(task: bk_series_pb2.TimerTask):
            for dev_target_soc in task.chg_task.dev_target_soc:
                if dev_target_soc.sn == sn:
                    modify_dev_target_soc(dev_target_soc)

        return await self._send_timer_task_packet(self._charging_task, modify)

    @controls.switch(
        charging_task_enabled,
        availability=dynamic(charging_grid_power_limit_enabled),
    )
    async def enable_charging_task(self, enable: bool):
        def modify(task: bk_series_pb2.TimerTask):
            task.is_enable = enable

        await self._send_timer_task_packet(self._charging_task, modify)

    @controls.switch(
        discharging_task_enabled,
        availability=dynamic(discharging_task_available),
    )
    async def enable_discharging_task(self, enable: bool):
        def modify(task: bk_series_pb2.TimerTask):
            task.is_enable = enable

        await self._send_timer_task_packet(self._discharging_task, modify)

    @controls.power(
        discharging_power_limit,
        max=dynamic(max_ac_out_power),
        availability=dynamic(discharging_task_available),
    )
    async def set_discharging_power_limit(self, limit: float):
        def modify(task: bk_series_pb2.TimerTask):
            task.home_need_power_limited = int(limit)

        return await self._send_timer_task_packet(self._discharging_task, modify)

    def _get_chain(self) -> _TimerTaskChain:
        if self._timer_task_chain is not None:
            return self._timer_task_chain

        chain_key = (
            frozenset(soc.sn for soc in self._charging_task.chg_task.dev_target_soc)
            if (
                self._charging_task is not None
                and len(self._charging_task.chg_task.dev_target_soc) > 0
            )
            else frozenset([self._sn])
        )

        if chain_key not in Device._timer_task_chains:
            Device._timer_task_chains[chain_key] = _TimerTaskChain()

        self._timer_task_chain = Device._timer_task_chains[chain_key]
        return self._timer_task_chain

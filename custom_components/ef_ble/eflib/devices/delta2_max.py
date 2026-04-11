from ..entity import controls
from ..entity.base import dynamic
from ..model import Mr350MpptHeart, Mr350PdHeartbeatDelta2Max
from ..packet import Packet
from ..props import computed_field, dataclass_attr_mapper, raw_field
from ._delta2_base import Delta2Base, pb_inv

pb_pd = dataclass_attr_mapper(Mr350PdHeartbeatDelta2Max)
pb_mppt = dataclass_attr_mapper(Mr350MpptHeart)


class Device(Delta2Base):
    """Delta 2 Max"""

    SN_PREFIX = (b"R351", b"R354")
    NAME_PREFIX = "EF-R35"

    ac_input_power = raw_field(pb_inv.input_watts)
    ac_charging_speed = raw_field(pb_inv.cfg_slow_chg_watts)
    dc_output_power = raw_field(pb_pd.car_watts)
    energy_backup = raw_field(pb_pd.watthisconfig, lambda x: x == 1)
    energy_backup_battery_level = raw_field(pb_pd.bp_power_soc)

    xt60_1_input_power = raw_field(pb_pd.pv1_charge_watts)
    xt60_2_input_power = raw_field(pb_pd.pv2_charge_watts)

    @computed_field
    def max_ac_charging_power(self) -> int:
        return 1800

    @property
    def pd_heart_type(self):
        return Mr350PdHeartbeatDelta2Max

    @property
    def mppt_heart_type(self):
        return Mr350MpptHeart

    @property
    def ac_commands_dst(self):
        return 0x04

    @controls.switch(energy_backup)
    async def enable_energy_backup(self, enabled: bool):
        backup_level = self.energy_backup_battery_level or 50
        await self._send_backup_packet(backup_level, enabled=enabled)

    @controls.battery(
        energy_backup_battery_level,
        min=dynamic(Delta2Base.battery_charge_limit_min),
        max=dynamic(Delta2Base.battery_charge_limit_max),
        availability=energy_backup,
    )
    async def set_energy_backup_battery_level(self, value: float):
        await self._send_backup_packet(int(value), enabled=True)
        return True

    async def _send_backup_packet(self, value: int, enabled: bool):
        if (
            self.battery_charge_limit_min is None
            or self.battery_charge_limit_max is None
        ):
            return
        value = max(
            self.battery_charge_limit_min,
            min(value, self.battery_charge_limit_max),
        )
        payload = bytes([0x01 if enabled else 0, value, 0x00, 0x00])
        await self._conn.sendPacket(
            Packet(0x21, 0x02, 0x20, 0x5E, payload, version=0x02)
        )

    @controls.power(ac_charging_speed, min=1, max=dynamic(max_ac_charging_power))
    async def set_ac_charging_speed(self, value: float):
        payload = bytes([0xFF, 0xFF]) + int(value).to_bytes(2, "little") + bytes([0xFF])
        await self._conn.sendPacket(
            Packet(0x20, 0x04, 0x20, 0x45, payload, version=0x02)
        )
        return True

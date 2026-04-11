from ..entity import controls
from ..entity.base import dynamic
from ..model import (
    Mr330MpptHeart,
    Mr330PdHeartDelta2,
)
from ..packet import Packet
from ..props import computed_field
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ._delta2_base import Delta2Base

pb_pd = dataclass_attr_mapper(Mr330PdHeartDelta2)
pb_mppt = dataclass_attr_mapper(Mr330MpptHeart)


class Device(Delta2Base):
    """Delta 2"""

    SN_PREFIX = (b"R331", b"R335")
    NAME_PREFIX = "EF-R33"

    ac_input_power = raw_field(pb_pd.ac_input_watts)
    energy_backup = raw_field(pb_pd.watthis_config, lambda x: x == 1)
    energy_backup_battery_level = raw_field(pb_pd.bp_power_soc)
    dc_output_power = raw_field(pb_pd.dc_pv_output_watts)
    ac_charging_speed = raw_field(pb_mppt.cfg_chg_watts)

    disable_grid_bypass = raw_field(pb_pd.reverser, lambda x: ((x >> 8) & 0xFF) == 1)

    xt60_input_power = raw_field(pb_pd.dc_pv_input_watts)

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    @property
    def pd_heart_type(self):
        return Mr330PdHeartDelta2

    @property
    def mppt_heart_type(self):
        return Mr330MpptHeart

    @computed_field
    def max_ac_charging_power(self) -> int:
        if self.battery_1_enabled or self.battery_2_enabled:
            return 1500
        return 1200

    def __init__(self, ble_dev, adv_data, sn: str) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._product_type: int | None = None

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
        packet = Packet(0x21, 0x02, 0x20, 0x5E, payload, version=0x02)
        await self._conn.sendPacket(packet)

    @controls.power(ac_charging_speed, min=1, max=dynamic(max_ac_charging_power))
    async def set_ac_charging_speed(self, value: float):
        payload = int(value).to_bytes(2, "little") + bytes([0xFF])
        packet = Packet(0x21, self.ac_commands_dst, 0x20, 0x45, payload, version=0x02)
        await self._conn.sendPacket(packet)
        return True

    @controls.switch(disable_grid_bypass, enabled=False)
    async def enable_disable_grid_bypass(self, disabled: bool):
        packet = Packet(
            0x21, 0x02, 0x20, 0x60, bytes([1 if disabled else 0]), version=0x02
        )
        await self._conn.sendPacket(packet)

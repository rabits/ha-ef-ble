from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..model import Mr350MpptHeart, Mr350PdHeartbeatDelta2Max
from ..packet import Packet
from ..props import dataclass_attr_mapper, raw_field
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

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self.max_ac_charging_power = 1800

    @property
    def pd_heart_type(self):
        return Mr350PdHeartbeatDelta2Max

    @property
    def mppt_heart_type(self):
        return Mr350MpptHeart

    @property
    def ac_commands_dst(self):
        return 0x04

    async def set_ac_charging_speed(self, value: int):
        if self.max_ac_charging_power is None:
            return False
        value = max(1, min(value, self.max_ac_charging_power))
        payload = bytes([0xFF, 0xFF]) + value.to_bytes(2, "little") + bytes([0xFF])
        await self._conn.sendPacket(
            Packet(0x20, 0x04, 0x20, 0x45, payload, version=0x02)
        )
        return True

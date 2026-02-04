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
    energy_backup_battery_level = raw_field(pb_pd.bp_power_soc)

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

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=False)

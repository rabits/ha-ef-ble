from ..model import (
    Mr330MpptHeart,
    Mr330PdHeartDelta2,
)
from ..packet import Packet
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ._delta2_base import Delta2Base

pb_pd = dataclass_attr_mapper(Mr330PdHeartDelta2)
pb_mppt = dataclass_attr_mapper(Mr330MpptHeart)


class Device(Delta2Base):
    """Delta 2"""

    SN_PREFIX = (b"R331", b"R335")
    NAME_PREFIX = "EF-R33"

    ac_input_power = raw_field(pb_pd.ac_input_watts)
    energy_backup_enabled = raw_field(pb_pd.watthis_config, lambda x: x == 1)
    energy_backup_battery_level = raw_field(pb_pd.bp_power_soc)
    dc_output_power = raw_field(pb_pd.dc_pv_output_watts)
    ac_charging_speed = raw_field(pb_mppt.cfg_chg_watts)

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    @property
    def pd_heart_type(self):
        return Mr330PdHeartDelta2

    @property
    def mppt_heart_type(self):
        return Mr330MpptHeart

    def __init__(self, ble_dev, adv_data, sn: str) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._product_type: int | None = None
        self.max_ac_charging_power = 1200

    def _after_message_parsed(self):
        self._update_ac_chg_limits()

    def _update_ac_chg_limits(self) -> None:
        if self.battery_addon:
            self.max_ac_charging_power = 1500
        else:
            self.max_ac_charging_power = 1200

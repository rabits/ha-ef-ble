from collections.abc import Sequence

from custom_components.ef_ble.eflib.pb import pd335_sys_pb2

from ..entity import controls
from ..props import pb_field, repeated_pb_field_type
from . import delta3, delta3_ultra
from ._delta3_base import flow_is_on, out_power

pb = delta3.pb


class _ACPortPower(repeated_pb_field_type(pb.pow_get_ac_out_list.pow_get_ac_out_item)):
    index: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return out_power(value[self.index]) if value else None


class Device(delta3_ultra.Device):
    """Delta 3 Ultra Plus"""

    SN_PREFIX = (b"D511",)
    NAME_PREFIX = "EF-D5"

    ac_ports_2 = pb_field(pb.flow_info_ac2_out, flow_is_on)

    ac_power_1_1 = _ACPortPower(0)
    ac_power_1_2 = _ACPortPower(1)
    ac_power_2_1 = _ACPortPower(2)
    ac_power_2_2 = _ACPortPower(3)
    ac_power_2_3 = _ACPortPower(4)

    usbc3_output_power = pb_field(pb.pow_get_typec3, out_power)
    max_ac_charging_power = pb_field(pb.plug_in_info_ac_in_chg_hal_pow_max)

    @controls.outlet(ac_ports_2)
    async def enable_ac_ports_2(self, enabled: bool):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_ac2_out_open=enabled)
        )

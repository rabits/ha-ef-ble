from collections.abc import Sequence

from ..entity import controls, dynamic
from ..pb import pd335_sys_pb2
from ..props import computed_field, pb_field, repeated_pb_field_type
from ..props.transforms import flow_is_on, out_power, pround
from . import delta3, delta3_ultra
from ._delta3_base import (
    DCPortState,
    Delta3Base,
    _DcAmpSettingField,
    _DcChargingMaxField,
)

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

    dc_charging_max_amps_2 = _DcAmpSettingField(
        pd335_sys_pb2.PV_CHG_VOL_SPEC_12V, pd335_sys_pb2.PV_PLUG_INDEX_2
    )
    dc_charging_current_max_2 = _DcChargingMaxField(pd335_sys_pb2.PV_CHG_VOL_SPEC_12V)

    dc_port_2_input_power = pb_field(pb.pow_get_pv2, pround(2))
    dc_port_2_state = pb_field(pb.plug_in_info_pv2_type, DCPortState.from_value)

    @computed_field
    def solar_input_power_2(self) -> float:
        if (
            self.dc_port_2_state is DCPortState.SOLAR
            and self.dc_port_2_input_power is not None
        ):
            return round(self.dc_port_2_input_power, 2)
        return 0

    @controls.current(
        dc_charging_max_amps_2,
        min=dynamic(Delta3Base.dc_charging_amps_min),
        max=dynamic(dc_charging_current_max_2),
    )
    async def set_dc_charging_amps_max_2(self, value: float) -> bool:
        return await self.set_dc_charging_amps_max(
            value, plug_index=pd335_sys_pb2.PV_PLUG_INDEX_2
        )

    @controls.outlet(ac_ports_2)
    async def enable_ac_ports_2(self, enabled: bool):
        await self._send_config_packet(
            pd335_sys_pb2.ConfigWrite(cfg_ac2_out_open=enabled)
        )

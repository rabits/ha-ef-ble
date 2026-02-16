from functools import partialmethod

from ..pb import pd335_sys_pb2
from ..props import Field, pb_field
from . import delta3
from ._delta3_base import DCPortState, _DcAmpSettingField, _DcChargingMaxField, pb


class Device(delta3.Device):
    """Delta 3 Plus"""

    SN_PREFIX = (b"P351",)

    dc_charging_max_amps_2 = _DcAmpSettingField(
        pd335_sys_pb2.PV_CHG_VOL_SPEC_12V, pd335_sys_pb2.PV_PLUG_INDEX_2
    )
    dc_charging_current_max_2 = _DcChargingMaxField(pd335_sys_pb2.PV_CHG_VOL_SPEC_12V)

    dc_port_2_input_power = pb_field(pb.pow_get_pv2, lambda value: round(value, 2))
    dc_port_2_state = pb_field(pb.plug_in_info_pv2_type, DCPortState.from_value)

    solar_input_power_2 = Field[float]()

    def _after_message_parsed(self):
        self.solar_input_power_2 = (
            round(self.dc_port_2_input_power, 2)
            if (
                self.dc_port_2_state is DCPortState.SOLAR
                and self.dc_port_2_input_power is not None
            )
            else 0
        )

    set_dc_charging_amps_max_2 = partialmethod(
        delta3.Device.set_dc_charging_amps_max, plug_index=pd335_sys_pb2.PV_PLUG_INDEX_2
    )

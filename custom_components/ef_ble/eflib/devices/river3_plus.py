from ..entity import controls
from ..pb import pr705_pb2
from ..props import pb_field
from ..props.enums import IntFieldValue
from ..props.resv_info_parser import resv_soc, resv_temperature
from . import river3

pb = river3.pb


class LedMode(IntFieldValue):
    OFF = 0
    DIM = 1
    BRIGHT = 2
    SOS = 3


class Device(river3.Device):
    """River 3 Plus"""

    SN_PREFIX = (b"R631", b"R634", b"R635")

    battery_level_main = pb_field(river3.pb.bms_batt_soc)

    battery_1_enabled = pb_field(pb.plug_in_info_dcp_in_flag)
    battery_1_battery_level = pb_field(pb.plug_in_info_dcp_resv, resv_soc)
    battery_1_cell_temperature = pb_field(pb.plug_in_info_dcp_resv, resv_temperature)
    battery_1_sn = pb_field(pb.plug_in_info_dcp_sn)

    led_mode = pb_field(river3.pb.led_mode, LedMode.from_value)

    @controls.select(led_mode, options=LedMode)
    async def set_led_mode(self, state: LedMode):
        await self._send_config_packet(pr705_pb2.ConfigWrite(cfg_led_mode=state.value))

    @property
    def device(self):
        model = ""
        match self._sn[:4]:
            case "R634":
                model = "(270)"
            case "R635":
                model = "Wireless"

        return f"River 3 Plus {model}".strip()

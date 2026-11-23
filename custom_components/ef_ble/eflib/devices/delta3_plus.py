from ..entity import controls
from ..entity.base import dynamic
from ..packet import Packet
from ..pb import pd335_sys_pb2
from ..props import Field, computed_field, pb_field
from ..props.transforms import pround
from . import delta3
from ._delta3_base import (
    DCPortState,
    Delta3Base,
    _DcAmpSettingField,
    _DcChargingMaxField,
    pb,
)

# Captured on DELTA 3 Plus (product 79 / detail 2). Other 03:2F layouts
# (extra battery, other Delta 3 variants) must not be decoded as the pack.
_STATION_PRODUCT = 79
_STATION_DETAIL = 2
_STATION_REPORT_LENGTH = 132
_STATION_VOLTAGE_MIN_MV = 30_000
_STATION_VOLTAGE_MAX_MV = 60_000
_STATION_REPORT_INTERVAL = 5


class Device(delta3.Device):
    """Delta 3 Plus"""

    SN_PREFIX = (b"P351",)

    # DisplayPropertyUpload over BLE does not carry pack voltage/current.
    battery_voltage = Field[float]()
    battery_current = Field[float]()

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

    def __init__(self, ble_dev, adv_data, sn):
        super().__init__(ble_dev, adv_data, sn)
        self.add_timer_task(
            self._request_station_report, interval=_STATION_REPORT_INTERVAL
        )

    async def _request_station_report(self) -> None:
        await self.send_packet(
            Packet(0x21, 0x03, 0x03, 0x2F, b""),
            wait_for_response=False,
        )

    async def data_parse(self, packet: Packet):
        if packet.src == 0x03 and packet.cmd_set == 0x03 and packet.cmd_id == 0x2F:
            self.reset_updated()
            self._update_from_station_report(packet.payload)
            self._notify_updated()
            return True
        return await super().data_parse(packet)

    def _update_from_station_report(self, payload: bytes) -> None:
        if len(payload) != _STATION_REPORT_LENGTH:
            return
        if payload[1] != _STATION_REPORT_LENGTH or payload[2] != 0:
            return
        if (
            payload[19] != _STATION_PRODUCT
            or payload[20] != 0
            or payload[21] != _STATION_DETAIL
            or payload[22] != 0
        ):
            return
        soc = payload[56]
        voltage_mv = int.from_bytes(payload[57:61], "little")
        if soc > 100 or not (
            _STATION_VOLTAGE_MIN_MV <= voltage_mv <= _STATION_VOLTAGE_MAX_MV
        ):
            return
        current_ma = int.from_bytes(payload[61:65], "little", signed=True)
        self.battery_voltage = round(voltage_mv / 1000, 3)
        self.battery_current = round(current_ma / 1000, 3)

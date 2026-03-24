"""EcoFlow PowerPulse EV charger (BLE / AC517 APL)."""

import logging

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from google.protobuf.message import DecodeError

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import ac517_powerpulse_ev_pb2
from ..props import Field, ProtobufProps
from ..props.enums import IntFieldValue
from ..props.utils import pround

_LOGGER = logging.getLogger(__name__)


class AcPlugState(IntFieldValue):
    UNKNOWN = -1
    UNPLUGGED = 0
    PLUGGED_IN = 1
    CHARGING = 2
    CHARGE_COMPLETE = 3


class Device(DeviceBase, ProtobufProps):
    """PowerPulse"""

    # Only C101 (9.6 kW US EV charger) is verified.
    # Other PowerPulse SKUs remain unsupported.
    SN_PREFIX = (b"C101",)
    NAME_PREFIX = "EF-PP"

    output_power = Field[float]()
    ac_output_voltage = Field[float]()
    ac_output_current = Field[float]()
    ac_plug_state = Field[AcPlugState]()

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self) -> str:
        return "EcoFlow PowerPulse EV Charger (9.6 kW)"

    async def packet_parse(self, data: bytes):
        return Packet.fromBytes(data, xor_payload=True)

    def _apply_plug_state(self, state: int | None, payload_len: int) -> None:
        if state == 1:
            self.ac_plug_state = AcPlugState.UNPLUGGED
            return
        if state == 2:
            self.ac_plug_state = AcPlugState.PLUGGED_IN
            return
        if state == 3:
            self.ac_plug_state = AcPlugState.CHARGING
            return
        if state == 6:
            self.ac_plug_state = AcPlugState.CHARGE_COMPLETE
            return
        if state is None and payload_len == 0:
            # Empty heartbeat carries no explicit plug state.
            self.ac_plug_state = AcPlugState.UNKNOWN

    def _apply_metrics(
        self, power_w: float | None, voltage_v: float | None, current_a: float | None
    ) -> None:
        # Small near-zero noise values can appear while unplugged/idle.
        if current_a is not None and abs(current_a) < 0.05:
            current_a = 0.0
        if power_w is not None and abs(power_w) < 1.0:
            power_w = 0.0

        if voltage_v is not None:
            self.ac_output_voltage = pround(1)(voltage_v)
        if current_a is not None:
            self.ac_output_current = pround(2)(current_a)
        if power_w is not None:
            self.output_power = pround(1)(power_w)

        if self.ac_output_voltage is None:
            self.ac_output_voltage = 0.0
        if self.ac_output_current is None:
            self.ac_output_current = 0.0
        if self.output_power is None:
            self.output_power = 0.0

    def _parse_status_packet(self, packet: Packet) -> bool:
        if packet.src != 0x02 or packet.cmdSet != 0x02 or packet.cmdId != 0x21:
            return False

        try:
            msg = self.update_from_bytes(
                ac517_powerpulse_ev_pb2.Cmd2_2_33Status, packet.payload
            )
        except DecodeError:
            return False

        state = msg.state if msg.state != 0 else None
        if msg.HasField("metrics"):
            metrics = msg.metrics
            power_w = float(metrics.power_w)
            voltage_v = float(metrics.voltage_v)
            current_a = float(metrics.current_a)
        else:
            power_w = voltage_v = current_a = None

        self._apply_plug_state(state=state, payload_len=len(packet.payload))
        self._apply_metrics(power_w=power_w, voltage_v=voltage_v, current_a=current_a)
        return True

    def _is_time_sync_request(self, packet: Packet) -> bool:
        return (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        )

    async def data_parse(self, packet: Packet) -> bool:
        self.reset_updated()
        processed = self._parse_status_packet(packet)

        if not processed and self._is_time_sync_request(packet):
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

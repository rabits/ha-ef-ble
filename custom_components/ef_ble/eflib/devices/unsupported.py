import time
from collections import deque

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from custom_components.ef_ble.eflib.connection import ConnectionState

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..logging_util import LogOptions
from ..packet import Packet


class UnsupportedDevice(DeviceBase):
    NAME_PREFIX = ""

    _last_payloads: deque[tuple[float, str]]
    _last_errors: deque[tuple[float, str]]
    _connect_times: deque[float]
    _disconnect_times: deque[float]
    _skip_first_messages: int = 8

    collecting_data: str = "connecting"

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)
        self._start_time = time.time()
        self._messages_skipped = 0

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return True

    @property
    def last_packets(self) -> deque[tuple[float, str]]:
        if not hasattr(self, "_last_payloads"):
            setattr(self, "_last_payloads", deque(maxlen=20))
        return self._last_payloads

    @property
    def last_errors(self) -> deque[tuple[float, str]]:
        if not hasattr(self, "_last_errors"):
            setattr(self, "_last_errors", deque(maxlen=20))
        return self._last_errors

    @property
    def disconnect_times(self) -> deque[float]:
        if not hasattr(self, "_disconnect_times"):
            setattr(self, "_disconnect_times", deque(maxlen=20))
        return self._disconnect_times

    def on_disconnected(self):
        self.disconnect_times.append(time.time() - self._start_time)

    def on_connection_state_change(self, state: ConnectionState):
        if state.is_error():
            self.collecting_data = "error"
            self.update_callback("collecting_data")
        return super().on_connection_state_change(state)

    @property
    def device(self):
        name = "Unknown Device"
        match self._sn[:4]:
            case "F371" | "F372":
                name = "Alternator Charger"
            case "DC01":
                name = "Alternator Charger (500W)"
            case "R331" | "R335":
                name = "Delta 2"
            case "R351" | "R354":
                name = "Delta 2 Max"
            case "H101":
                name = "Blade"
            case "BX11":
                name = "GLACIER"
            case "RF43":
                name = "GLACIER 2 (35L)"
            case "RF44":
                name = "GLACIER 2 (45L)"
            case "RF45":
                name = "GLACIER 2 (55L)"
            case "P535" | "P53D" | "P53F" | "P53E":
                name = "RAPID (10000mAh)"
            case "R601" | "R603":
                name = "River 2"
            case "R611" | "R613":
                name = "River 2 Max"
            case "R621" | "R623":
                name = "River 2 Pro"
            case "M201":
                name = "Wave"
            case "KT21":
                name = "Wave 2"
            case "AC71":
                name = "Wave 3"
            case "HJ31":
                name = "PowerOcean"
            case "HJ35":
                name = "PowerOcean (6kW)"
            case "HJ37":
                name = "PowerOcean (12kW)"
            case "HW51":
                name = "PowerStream"
            case "R635":
                name = "River 3 Plus Wireless"
            case "HR62":
                name = "Smart Home Panel 3"
            case "R655":
                name = "River 3 (245Wh)"
        return f"[Unsupported] {name}"

    async def packet_parse(self, data: bytes) -> Packet:
        self.collecting_data = "collecting"
        self.last_packets.append(
            (time.time() - self._start_time, bytearray(data).hex())
        )
        if len(self.last_packets) == self.last_packets.maxlen:
            self._messages_skipped += 1
            if self._messages_skipped < self._skip_first_messages:
                self.last_packets.pop()
            else:
                self.collecting_data = "done"

        packet = Packet.fromBytes(data, is_xor=True, return_error=True)
        if isinstance(packet, str):
            self.last_errors.append((time.time() - self._start_time, packet))
            self.collecting_data = "error"
            self.update_callback("collecting_data")
            return None

        self.update_callback("collecting_data")
        return packet

    async def data_parse(self, packet: Packet) -> bool:
        self._logger.log_filtered(
            LogOptions.DESERIALIZED_MESSAGES, "Device message: %r", packet.payloadHex
        )
        processed = False

        if (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        return processed

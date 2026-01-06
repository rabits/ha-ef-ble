import time
from collections import deque

from ..devicebase import DeviceBase
from ..logging_util import LogOptions
from ..packet import Packet


class Device(DeviceBase):
    NAME_PREFIX = ""

    _last_xor_payloads: deque[tuple[float, str]]
    _last_payloads: deque[tuple[float, str]]

    collecting_data: bool = False

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return True

    @property
    def last_xor_payloads(self) -> deque[tuple[float, str]]:
        if not hasattr(self, "_last_xor_payloads"):
            setattr(self, "_last_xor_payloads", deque(maxlen=10))
        return self._last_xor_payloads

    @property
    def last_payloads(self) -> deque[tuple[float, str]]:
        if not hasattr(self, "_last_payloads"):
            setattr(self, "_last_payloads", deque(maxlen=10))
        return self._last_payloads

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
        packet = Packet.fromBytes(data, is_xor=False)
        packet_xor = Packet.fromBytes(data, is_xor=True)

        self.last_payloads.append((time.time(), packet.payloadHex))
        self.last_xor_payloads.append((time.time(), packet_xor.payloadHex))

        self.collecting_data = True
        if len(self.last_payloads) == self.last_payloads.maxlen:
            self.collecting_data = False

        self.update_state("collecting_data", self.collecting_data)

        return packet_xor

    async def data_parse(self, packet: Packet) -> bool:
        self._logger.log_filtered(
            LogOptions.DESERIALIZED_MESSAGES, "Device message: %r", packet.payloadHex
        )
        return await super().data_parse(packet)

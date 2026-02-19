from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..device_mappings import ECOFLOW_DEVICE_LIST
from ..devicebase import DeviceBase
from ..logging_util import LogOptions
from ..packet import Packet


class UnsupportedDevice(DeviceBase):
    collecting_data: str = "connecting"

    @property
    def NAME_PREFIX(self):
        return f"u-EF-{self._sn[:2]}"

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)
        self._diagnostics.enabled()

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return True

    @property
    def device(self):
        name = "Unidentified Device"
        for i in [5, 4, 3, 2]:
            if self._sn[:i] in ECOFLOW_DEVICE_LIST:
                name = ECOFLOW_DEVICE_LIST[self._sn[:i]]["name"]
                break

        return f"[Unsupported] {name}"

    @property
    def packet_version(self):
        version = 0x03
        for i in [5, 4, 3, 2]:
            if self._sn[:i] in ECOFLOW_DEVICE_LIST:
                version = (
                    0x02
                    if ECOFLOW_DEVICE_LIST[self._sn[:i]]["packets"] in ["v2", "v1"]
                    else 0x03
                )
                break

        return version

    @property
    def auth_header_dst(self):
        return (
            0x32
            if self._sn.startswith("DC")
            or self._sn.startswith("R511")
            or self._sn.startswith("Z0")
            else 0x35
        )

    def with_update_period(self, period: int):
        # NOTE(gnox): as unsupported devices do not have any sensors, we leave update
        # period to default, otherwise collection sensor would lag
        return self

    async def packet_parse(self, data: bytes) -> Packet:
        self.collecting_data = "collecting"

        if self._diagnostics.packet_target_reached:
            self.collecting_data = "done"
        else:
            self.collecting_data = f"{self._diagnostics.packets_collected}/{self._diagnostics.packet_buffer_size}"

        packet = Packet.fromBytes(data)
        if Packet.is_invalid(packet):
            self.collecting_data = "error"

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

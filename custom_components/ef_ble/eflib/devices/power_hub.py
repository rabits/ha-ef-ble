"""EcoFlow Power Kits Power Hub support."""

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..connection import ConnectionState
from ..devicebase import DeviceBase
from ..model import PowerHubBatteryData, PowerHubBmsData, PowerHubMpptData
from ..packet import Packet
from ..props import Field, RawDataProps, field_group
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.transforms import pdiv

bms = dataclass_attr_mapper(PowerHubBmsData)
mppt = dataclass_attr_mapper(PowerHubMpptData)
millivolts_to_volts = pdiv(1000, 3)


class Device(DeviceBase, RawDataProps):
    """Power Kits Power Hub"""

    SN_PREFIX = (b"M109",)
    NAME_PREFIX = "EF-M10"

    battery_level = raw_field(bms.soc)
    input_power = raw_field(bms.input_power)
    output_power = raw_field(bms.output_power)

    battery_voltage = raw_field(mppt.battery_voltage, millivolts_to_volts)
    battery_current = raw_field(mppt.battery_current, pdiv(1000, 3))
    pv_voltage_1 = raw_field(mppt.pv_voltage_1, millivolts_to_volts)
    pv_current_1 = raw_field(mppt.pv_current_1, pdiv(1000, 3))
    pv_power_1 = raw_field(mppt.pv_power_1)
    pv_voltage_2 = raw_field(mppt.pv_voltage_2, millivolts_to_volts)
    pv_current_2 = raw_field(mppt.pv_current_2, pdiv(1000, 3))
    pv_power_2 = raw_field(mppt.pv_power_2)
    pv_heatsink_temperature_1 = raw_field(mppt.heatsink_temperature_1)
    pv_heatsink_temperature_2 = raw_field(mppt.heatsink_temperature_2)
    pcb_temperature = raw_field(mppt.pcb_temperature)

    battery_enabled = field_group(
        lambda _: Field[bool](), 3, name_template="battery_{n}_enabled"
    )
    battery_sn = field_group(lambda _: Field[str](), 3, name_template="battery_{n}_sn")
    battery_battery_level = field_group(
        lambda _: Field[int](), 3, name_template="battery_{n}_battery_level"
    )
    battery_pack_temperature = field_group(
        lambda _: Field[int](), 3, name_template="battery_{n}_battery_temperature"
    )
    battery_max_cell_temperature = field_group(
        lambda _: Field[int](), 3, name_template="battery_{n}_max_cell_temperature"
    )
    battery_min_cell_temperature = field_group(
        lambda _: Field[int](), 3, name_template="battery_{n}_min_cell_temperature"
    )
    extra_battery_voltage = field_group(
        lambda _: Field[float](), 3, name_template="battery_{n}_voltage"
    )
    battery_max_cell_voltage = field_group(
        lambda _: Field[float](), 3, name_template="battery_{n}_max_cell_voltage"
    )
    battery_min_cell_voltage = field_group(
        lambda _: Field[float](), 3, name_template="battery_{n}_min_cell_voltage"
    )
    battery_pack_input_power = field_group(
        lambda _: Field[int](), 3, name_template="battery_{n}_input_power"
    )
    battery_pack_output_power = field_group(
        lambda _: Field[int](), 3, name_template="battery_{n}_output_power"
    )

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)
        self._seen_battery_slots: set[int] = set()
        self.on_connection_state_change(self._track_battery_slots)

    def _track_battery_slots(self, state: ConnectionState) -> None:
        if state is not ConnectionState.AUTHENTICATED:
            return
        self._seen_battery_slots.clear()
        self.call_later(5, self._expire_missing_batteries, key="power_hub_batteries")

    def _expire_missing_batteries(self) -> None:
        for index in range(1, 4):
            if index in self._seen_battery_slots:
                continue
            self.set_value(Device.battery_enabled[index], False)
            for field in (
                Device.battery_battery_level[index],
                Device.extra_battery_voltage[index],
                Device.battery_pack_temperature[index],
                Device.battery_max_cell_temperature[index],
                Device.battery_min_cell_temperature[index],
                Device.battery_max_cell_voltage[index],
                Device.battery_min_cell_voltage[index],
                Device.battery_pack_input_power[index],
                Device.battery_pack_output_power[index],
            ):
                self.set_value(field, None)
        self._notify_updated()

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return sn[:4] in cls.SN_PREFIX

    async def packet_parse(self, data: bytes) -> Packet:
        # Power Hub uses the v3/0x13 payload XOR convention.
        return Packet.from_bytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet) -> bool:
        self.reset_updated()

        match packet.src, packet.cmd_set, packet.cmd_id:
            case (0x03, 0x03, 0x1A) if 1 <= packet.dsrc <= 3:
                battery = self.update_from_bytes(PowerHubBatteryData, packet.payload)
                self._update_battery(packet.dsrc, battery)
            case (0x03, 0x03, 0x1C):
                self.update_from_bytes(PowerHubBmsData, packet.payload)
            case (0x05, 0x05, 0x20):
                self.update_from_bytes(PowerHubMpptData, packet.payload)
            case (
                0x35,
                0x01,
                Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME,
            ):
                if not packet.payload:
                    self._time_commands.async_send_all()
                return True
            case _:
                return False

        self._notify_updated()
        return True

    def _update_battery(self, index: int, data: PowerHubBatteryData) -> None:
        self._seen_battery_slots.add(index)
        self.set_value(Device.battery_enabled[index], True)
        self.set_value(
            Device.battery_sn[index],
            data.sn.rstrip(b"\x00").decode("ASCII", errors="replace"),
        )
        self.set_value(Device.battery_battery_level[index], data.soc)
        self.set_value(
            Device.extra_battery_voltage[index], millivolts_to_volts(data.voltage)
        )
        self.set_value(Device.battery_pack_temperature[index], data.battery_temperature)
        self.set_value(
            Device.battery_max_cell_temperature[index], data.max_cell_temperature
        )
        self.set_value(
            Device.battery_min_cell_temperature[index], data.min_cell_temperature
        )
        self.set_value(
            Device.battery_max_cell_voltage[index],
            millivolts_to_volts(data.max_cell_voltage),
        )
        self.set_value(
            Device.battery_min_cell_voltage[index],
            millivolts_to_volts(data.min_cell_voltage),
        )
        self.set_value(Device.battery_pack_input_power[index], data.input_power)
        self.set_value(Device.battery_pack_output_power[index], data.output_power)

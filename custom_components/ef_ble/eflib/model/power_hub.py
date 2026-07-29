from typing import Annotated

from .base import RawData


class PowerHubBmsData(RawData):
    """Aggregate Power Hub battery-management record."""

    soc: Annotated[int, "B"]
    reserved_1: Annotated[bytes, "1s"]
    input_power: Annotated[int, "H"]
    reserved_4: Annotated[bytes, "2s"]
    output_power: Annotated[int, "h"]
    reserved_8: Annotated[bytes, "2s"]
    remaining_time: Annotated[int, "H"]


class PowerHubBatteryData(RawData):
    """Power Kits LFP battery record."""

    sn: Annotated[bytes, "16s"]
    reserved_16: Annotated[bytes, "21s"]
    soc: Annotated[int, "B"]
    voltage: Annotated[int, "H"]
    reserved_40: Annotated[bytes, "6s"]
    cell_temperature: Annotated[int, "B"]
    reserved_47: Annotated[bytes, "18s"]
    max_cell_voltage: Annotated[int, "H"]
    reserved_67: Annotated[bytes, "2s"]
    min_cell_voltage: Annotated[int, "H"]
    reserved_71: Annotated[bytes, "7s"]
    input_power: Annotated[int, "I"]
    output_power: Annotated[int, "i"]


class PowerHubMpptData(RawData):
    """Power Hub solar-controller record."""

    reserved_0: Annotated[bytes, "28s"]
    battery_voltage: Annotated[int, "H"]
    reserved_30: Annotated[bytes, "2s"]
    battery_current: Annotated[int, "H"]
    reserved_34: Annotated[bytes, "6s"]
    pv_voltage_1: Annotated[int, "I"]
    pv_current_1: Annotated[int, "H"]
    reserved_46: Annotated[bytes, "2s"]
    pv_power_1: Annotated[int, "H"]
    reserved_50: Annotated[bytes, "2s"]
    pv_voltage_2: Annotated[int, "I"]
    pv_current_2: Annotated[int, "H"]
    reserved_58: Annotated[bytes, "2s"]
    pv_power_2: Annotated[int, "H"]
    reserved_62: Annotated[bytes, "10s"]
    pv_temperature_1: Annotated[int, "B"]
    reserved_73: Annotated[bytes, "1s"]
    pv_temperature_2: Annotated[int, "B"]

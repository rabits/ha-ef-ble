from typing import Annotated

from .base import RawData


class PowerHubBmsData(RawData):
    """Aggregate Power Hub battery-management record."""

    soc: Annotated[int, "B"]
    charge_discharge_state: Annotated[int, "B"]
    input_power: Annotated[int, "i"]
    output_power: Annotated[int, "i"]
    remaining_time: Annotated[int, "H"]


class PowerHubBatteryData(RawData):
    """Power Kits LFP battery record."""

    sn: Annotated[bytes, "16s"]
    reserved_16: Annotated[bytes, "21s"]
    soc: Annotated[int, "B"]
    voltage: Annotated[int, "i"]
    current: Annotated[int, "i"]
    battery_temperature: Annotated[int, "b"]
    charge_state: Annotated[int, "B"]
    open_bms_state: Annotated[int, "B"]
    design_capacity: Annotated[int, "i"]
    full_capacity: Annotated[int, "i"]
    remaining_capacity: Annotated[int, "i"]
    cycle_count: Annotated[int, "i"]
    max_cell_voltage: Annotated[int, "i"]
    min_cell_voltage: Annotated[int, "i"]
    max_cell_temperature: Annotated[int, "b"]
    min_cell_temperature: Annotated[int, "b"]
    mos_temperature_1: Annotated[int, "b"]
    mos_temperature_2: Annotated[int, "b"]
    bms_fault: Annotated[int, "B"]
    input_power: Annotated[int, "i"]
    output_power: Annotated[int, "i"]
    remaining_time: Annotated[int, "i"]


class PowerHubMpptData(RawData):
    """Power Hub solar-controller record."""

    reserved_0: Annotated[bytes, "28s"]
    battery_voltage: Annotated[int, "i"]
    battery_current: Annotated[int, "i"]
    battery_power: Annotated[int, "i"]
    pv_voltage_1: Annotated[int, "i"]
    pv_current_1: Annotated[int, "i"]
    pv_power_1: Annotated[int, "i"]
    pv_voltage_2: Annotated[int, "i"]
    pv_current_2: Annotated[int, "i"]
    pv_power_2: Annotated[int, "i"]
    l1_current: Annotated[int, "i"]
    l2_current: Annotated[int, "i"]
    heatsink_temperature_1: Annotated[int, "h"]
    heatsink_temperature_2: Annotated[int, "h"]
    pcb_temperature: Annotated[int, "h"]

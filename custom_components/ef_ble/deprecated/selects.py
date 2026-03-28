"""Deprecated: hardcoded select entity descriptions for unmigrated devices"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntityDescription

from ..eflib import DeviceBase
from ..eflib.devices import (
    alternator_charger,
    dpu,
    powerstream,
    river2,
    river3,
    river3_plus,
    shp2,
    smart_generator,
    stream_ac,
    wave2,
)


@dataclass(kw_only=True, frozen=True)
class EcoflowSelectEntityDescription[T: DeviceBase](SelectEntityDescription):
    set_state: Callable[[T, str], Awaitable] | None = None
    availability_prop: str | None = None


SELECT_TYPES: list[EcoflowSelectEntityDescription] = [
    EcoflowSelectEntityDescription[river3_plus.Device](
        key="led_mode",
        options=river3_plus.LedMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_led_mode(
                river3_plus.LedMode[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[river3.Device](
        key="dc_charging_type",
        name="DC Charging Type",
        options=river3.DcChargingType.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_dc_charging_type(
                river3.DcChargingType[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[river2.Device](
        key="dc_mode",
        name="DC Mode",
        options=river2.DCMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_dc_mode(river2.DCMode[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[smart_generator.Device](
        key="performance_mode",
        options=smart_generator.PerformanceMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_performance_mode(
                smart_generator.PerformanceMode[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[smart_generator.Device](
        key="liquefied_gas_unit",
        options=smart_generator.LiquefiedGasUnit.options(include_unknown=False),
        availability_prop="lpg_level_monitoring",
        set_state=(
            lambda device, value: device.set_liquefied_gas_unit(
                smart_generator.LiquefiedGasUnit[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[alternator_charger.Device](
        key="charger_mode",
        options=alternator_charger.ChargerMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_charger_mode(
                alternator_charger.ChargerMode[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[stream_ac.Device](
        key="energy_strategy",
        name="Energy Strategy",
        options=stream_ac.EnergyStrategy.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_energy_strategy(
                stream_ac.EnergyStrategy[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="power_mode",
        name="Power Mode",
        options=wave2.PowerMode.options(
            include_unknown=False, exclude=[wave2.PowerMode.INIT]
        ),
        set_state=(
            lambda device, value: device.set_power_mode(wave2.PowerMode[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="main_mode",
        name="Main Mode",
        options=wave2.MainMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_main_mode(wave2.MainMode[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="sub_mode",
        name="Sub Mode",
        options=wave2.SubMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_sub_mode(wave2.SubMode[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="fan_speed",
        name="Fan Speed",
        options=wave2.FanGear.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_fan_speed(wave2.FanGear[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="drain_mode",
        name="Drain Mode",
        options=wave2.DrainMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_drain_mode(wave2.DrainMode[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[powerstream.Device](
        key="power_supply_priority",
        name="Power Supply Priority",
        options=powerstream.PowerSupplyPriority.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_supply_priority(
                powerstream.PowerSupplyPriority[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[shp2.Device](
        key="smart_backup_mode",
        options=shp2.SmartBackupMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_smart_backup_mode(
                shp2.SmartBackupMode[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[dpu.Device](
        key="operating_mode_select",
        options=dpu.OperatingMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_operating_mode(
                dpu.OperatingMode[value.upper()]
            )
        ),
    ),
]

"""Deprecated: hardcoded number entity descriptions for unmigrated devices"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)

from ..eflib import DeviceBase
from ..eflib.devices import (
    alternator_charger,
    delta3_classic,
    delta3_plus,
    delta_pro_3,
    dpu,
    powerstream,
    river2,
    river3,
    shp2,
    smart_generator,
    smart_generator_4k,
    stream_ac,
    stream_microinverter,
    wave2,
)


@dataclass(frozen=True, kw_only=True)
class EcoflowNumberEntityDescription[Device: DeviceBase](NumberEntityDescription):
    async_set_native_value: Callable[[Device, float], Awaitable[bool]] | None = None
    native_unit_of_measurement_field: Callable[[Device], str] | None = None

    min_value_prop: str | None = None
    max_value_prop: str | None = None
    step_value_prop: str | None = None
    availability_prop: str | None = None


NUMBER_TYPES: list[EcoflowNumberEntityDescription] = [
    EcoflowNumberEntityDescription[river3.Device](
        key="energy_backup_battery_level",
        name="Backup Reserve",
        icon="mdi:battery-sync",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        min_value_prop="battery_charge_limit_min",
        max_value_prop="battery_charge_limit_max",
        async_set_native_value=(
            lambda device, value: device.set_energy_backup_battery_level(int(value))
        ),
        availability_prop="energy_backup",
    ),
    EcoflowNumberEntityDescription[river3.Device](
        key="battery_charge_limit_min",
        name="Discharge Limit",
        icon="mdi:battery-arrow-down-outline",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        native_min_value=0,
        max_value_prop="battery_charge_limit_max",
        async_set_native_value=(
            lambda device, value: device.set_battery_charge_limit_min(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[river3.Device](
        key="battery_charge_limit_max",
        name="Charge Limit",
        icon="mdi:battery-arrow-up",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        native_max_value=100,
        min_value_prop="battery_charge_limit_min",
        async_set_native_value=(
            lambda device, value: device.set_battery_charge_limit_max(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[
        river3.Device
        | delta3_classic.Device
        | delta_pro_3.Device
        | river2.Device
        | shp2.Device
    ](
        key="ac_charging_speed",
        name="AC Charging Speed",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        step_value_prop="ac_charging_speed_step",
        min_value_prop="min_ac_charging_power",
        max_value_prop="max_ac_charging_power",
        async_set_native_value=(
            lambda device, value: device.set_ac_charging_speed(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[
        river3.Device | delta3_classic.Device | river2.Device
    ](
        key="dc_charging_max_amps",
        name="DC Charging Max Amps",
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_step=1,
        native_min_value=0,
        max_value_prop="dc_charging_current_max",
        async_set_native_value=(
            lambda device, value: device.set_dc_charging_amps_max(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[delta3_plus.Device](
        key="dc_charging_max_amps_2",
        name="DC (2) Charging Max Amps",
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_step=1,
        native_min_value=0,
        max_value_prop="dc_charging_current_max_2",
        async_set_native_value=(
            lambda device, value: device.set_dc_charging_amps_max_2(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[smart_generator.Device](
        key="liquefied_gas_value",
        name="Gas Weight",
        native_min_value=0,
        native_step=0.1,
        availability_prop="lpg_level_monitoring",
        mode=NumberMode.BOX,
        async_set_native_value=(
            lambda device, value: device.set_liquefied_gas_value(value)
        ),
    ),
    EcoflowNumberEntityDescription[smart_generator_4k.Device](
        key="dc_output_power_limit",
        name="DC Power Limit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        mode=NumberMode.SLIDER,
        native_step=100,
        min_value_prop="dc_output_power_min",
        max_value_prop="dc_output_power_max",
        async_set_native_value=(
            lambda device, value: device.set_dc_output_power_max(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[alternator_charger.Device](
        key="power_limit",
        name="Power Limit",
        max_value_prop="power_max",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        async_set_native_value=(
            lambda device, value: device.set_power_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[alternator_charger.Device](
        key="start_voltage",
        name="Start Voltage",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_step=0.1,
        min_value_prop="start_voltage_min",
        max_value_prop="start_voltage_max",
        async_set_native_value=(
            lambda device, value: device.set_battery_voltage(value)
        ),
    ),
    EcoflowNumberEntityDescription[alternator_charger.Device](
        key="reverse_charging_current_limit",
        name="Reverse Charging Current",
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_step=0.1,
        native_min_value=0,
        max_value_prop="reverse_charging_current_max",
        async_set_native_value=(
            lambda device, value: device.set_car_battery_curent_charge_limit(value)
        ),
    ),
    EcoflowNumberEntityDescription[alternator_charger.Device](
        key="charging_current_limit",
        name="Charging Current",
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_step=1,
        native_min_value=0,
        max_value_prop="charging_current_max",
        async_set_native_value=(
            lambda device, value: device.set_device_battery_current_charge_limit(value)
        ),
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="feed_grid_pow_limit",
        name="Feed Grid Power Limit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="feed_grid_pow_max",
        async_set_native_value=(
            lambda device, value: device.set_feed_grid_pow_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="base_load_power",
        name="Base Load Power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="feed_grid_pow_max",
        async_set_native_value=(
            lambda device, value: device.set_load_power(int(value))
        ),
        availability_prop="load_power_enabled",
    ),
    EcoflowNumberEntityDescription[powerstream.Device](
        key="load_power",
        name="Load Power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=0.1,
        native_min_value=0,
        max_value_prop="load_power_max",
        async_set_native_value=lambda device, value: device.set_load_power(value),
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="grid_in_power_limit",
        name="Grid Input Power Limit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="max_ac_in_power",
        async_set_native_value=(
            lambda device, value: device.set_grid_in_pow_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="charging_grid_power_limit",
        name="Charging Power Limit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=100,
        native_min_value=0,
        max_value_prop="max_bp_input",
        async_set_native_value=(
            lambda device, value: device.set_charging_grid_power_limit(int(value))
        ),
        availability_prop="charging_grid_power_limit_enabled",
    ),
    EcoflowNumberEntityDescription[wave2.Device](
        key="target_temperature",
        name="Temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_step=1,
        native_min_value=16,
        native_max_value=30,
        async_set_native_value=(
            lambda device, value: device.set_temperature(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[stream_ac.Device](
        key="charging_grid_target_soc",
        name="Charging Target SOC",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        async_set_native_value=(
            lambda device, value: device.set_charging_grid_target_soc(int(value))
        ),
        availability_prop="charging_grid_power_limit_enabled",
    ),
    EcoflowNumberEntityDescription[stream_microinverter.Device](
        key="feed_grid_mode_power_limit",
        name="Maximum Output Power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=1,
        native_min_value=0,
        max_value_prop="feed_grid_mode_power_max",
        async_set_native_value=(
            lambda device, value: device.set_feed_grid_mode_pow_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device | shp2.Device](
        key="backup_reserve_level",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        min_value_prop="backup_reserve_level_min",
        max_value_prop="backup_reserve_level_max",
        availability_prop="backup_reserve_level_availability",
        async_set_native_value=(
            lambda device, value: device.set_backup_reserve_level(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device](
        key="backup_discharge_limit",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        min_value_prop="backup_discharge_limit_min",
        max_value_prop="backup_discharge_limit_max",
        async_set_native_value=(
            lambda device, value: device.set_backup_discharge_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device | shp2.Device](
        key="backup_charge_limit",
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_step=1.0,
        min_value_prop="backup_charge_limit_min",
        max_value_prop="backup_charge_limit_max",
        availability_prop="backup_charge_limit_availability",
        async_set_native_value=(
            lambda device, value: device.set_backup_charge_limit(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device](
        key="ac_5p8_charging_power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=100,
        min_value_prop="ac_5p8_min_charging_power",
        max_value_prop="ac_5p8_max_charging_power",
        async_set_native_value=(
            lambda device, value: device.set_ac_5p8_charging_power(int(value))
        ),
    ),
    EcoflowNumberEntityDescription[dpu.Device](
        key="ac_c20_charging_power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_step=100,
        min_value_prop="ac_c20_min_charging_power",
        max_value_prop="ac_c20_max_charging_power",
        availability_prop="ac_c20_charging_power_availability",
        async_set_native_value=(
            lambda device, value: device.set_ac_c20_charging_power(int(value))
        ),
    ),
]

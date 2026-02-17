"""EcoFlow BLE sensor"""

import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceConfigEntry
from .eflib import DeviceBase
from .eflib.devices import (
    _delta3_base,
    delta_pro_3,
    shp2,
    smart_generator,
    wave2,
    wave3,
)
from .entity import EcoflowEntity

_UPPER_WORDS = ["ac", "dc", "lv", "hv", "tt", "5p8"]


def _auto_name_from_key(key: str):
    return " ".join(
        [
            part.capitalize() if part.lower() not in _UPPER_WORDS else part.upper()
            for part in key.split("_")
        ]
    )


def _create_shp2_backup_channel_sensors():
    """Create sensor descriptions for SHP2 backup channel info"""
    sensors = {}

    for i in range(1, shp2.Device.NUM_OF_CHANNELS + 1):
        sensors.update(
            {
                f"ch{i}_ctrl_status": SensorEntityDescription(
                    key=f"ch{i}_ctrl_status",
                    device_class=SensorDeviceClass.ENUM,
                    options=shp2.ControlStatus.options(include_unknown=False),
                    translation_key="backup_ctrl_status",
                    translation_placeholders={"channel": f"{i}"},
                ),
                f"ch{i}_force_charge": SensorEntityDescription(
                    key=f"ch{i}_force_charge",
                    device_class=SensorDeviceClass.ENUM,
                    options=shp2.ForceChargeStatus.options(include_unknown=False),
                    translation_key="backup_force_charge",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                ),
                f"ch{i}_backup_rly1_cnt": SensorEntityDescription(
                    key=f"ch{i}_backup_rly1_cnt",
                    state_class=SensorStateClass.TOTAL,
                    translation_key="backup_relay1_count",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
                f"ch{i}_backup_rly2_cnt": SensorEntityDescription(
                    key=f"ch{i}_backup_rly2_cnt",
                    state_class=SensorStateClass.TOTAL,
                    translation_key="backup_relay2_count",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
                f"ch{i}_wake_up_charge_status": SensorEntityDescription(
                    key=f"ch{i}_wake_up_charge_status",
                    native_unit_of_measurement=PERCENTAGE,
                    device_class=SensorDeviceClass.BATTERY,
                    state_class=SensorStateClass.MEASUREMENT,
                    translation_key="backup_wakeup_charge",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                ),
                f"ch{i}_5p8_type": SensorEntityDescription(
                    key=f"ch{i}_5p8_type",
                    translation_key="backup_connector_type",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            }
        )

    return sensors


def _create_shp2_channel_sensors():
    """Create sensor descriptions for SHP2 channel info"""
    sensors = {}

    for i in range(1, shp2.Device.NUM_OF_CHANNELS + 1):
        sensors.update(
            {
                f"channel{i}_sn": SensorEntityDescription(
                    key=f"channel{i}_sn",
                    translation_key="channel_serial_number",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
                f"channel{i}_type": SensorEntityDescription(
                    key=f"channel{i}_type",
                    translation_key="channel_device_type",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
                f"channel{i}_capacity": SensorEntityDescription(
                    key=f"channel{i}_capacity",
                    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
                    device_class=SensorDeviceClass.ENERGY_STORAGE,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                    translation_key="channel_full_capacity",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                ),
                f"channel{i}_rate_power": SensorEntityDescription(
                    key=f"channel{i}_rate_power",
                    native_unit_of_measurement=UnitOfPower.WATT,
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    translation_key="channel_rated_power",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                ),
                f"channel{i}_battery_percentage": SensorEntityDescription(
                    key=f"channel{i}_battery_percentage",
                    native_unit_of_measurement=PERCENTAGE,
                    device_class=SensorDeviceClass.BATTERY,
                    state_class=SensorStateClass.MEASUREMENT,
                    translation_key="channel_battery_level",
                    translation_placeholders={"channel": f"{i}"},
                ),
                f"channel{i}_output_power": SensorEntityDescription(
                    key=f"channel{i}_output_power",
                    native_unit_of_measurement=UnitOfPower.WATT,
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=1,
                    translation_key="channel_output_power",
                    translation_placeholders={"channel": f"{i}"},
                ),
                f"channel{i}_battery_temp": SensorEntityDescription(
                    key=f"channel{i}_battery_temp",
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    state_class=SensorStateClass.MEASUREMENT,
                    translation_key="channel_battery_temperature",
                    translation_placeholders={"channel": f"{i}"},
                ),
                f"channel{i}_lcd_input": SensorEntityDescription(
                    key=f"channel{i}_lcd_input",
                    native_unit_of_measurement=UnitOfPower.WATT,
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    translation_key="channel_lcd_input_power",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                ),
                f"channel{i}_pv_status": SensorEntityDescription(
                    key=f"channel{i}_pv_status",
                    device_class=SensorDeviceClass.ENUM,
                    options=shp2.PVStatus.options(include_unknown=False),
                    translation_key="channel_pv_status",
                    translation_placeholders={"channel": f"{i}"},
                    entity_registry_enabled_default=False,
                ),
                f"channel{i}_pv_lv_input": SensorEntityDescription(
                    key=f"channel{i}_pv_lv_input",
                    native_unit_of_measurement=UnitOfPower.WATT,
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    translation_key="channel_pv_lv_input_power",
                    translation_placeholders={"channel": f"{i}"},
                ),
                f"channel{i}_pv_hv_input": SensorEntityDescription(
                    key=f"channel{i}_pv_hv_input",
                    native_unit_of_measurement=UnitOfPower.WATT,
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    translation_key="channel_pv_hv_input_power",
                    translation_placeholders={"channel": f"{i}"},
                ),
                f"channel{i}_error_code": SensorEntityDescription(
                    key=f"channel{i}_error_code",
                    state_class=SensorStateClass.MEASUREMENT,
                    translation_key="channel_error_count",
                    translation_placeholders={"channel": f"{i}"},
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            }
        )

    return sensors


@dataclass(frozen=True, kw_only=True)
class EcoflowSensorEntityDescription[Device: DeviceBase](SensorEntityDescription):
    state_attribute_fields: list[str] = field(default_factory=list)
    native_unit_of_measurement_field: str | Callable[[Device], str] | None = None


def _wave_unit(dev: wave3.Device):
    match dev:
        case wave3.Device:
            return (
                UnitOfTemperature.FAHRENHEIT
                if dev.temp_unit is wave3.TemperatureUnit.FAHRENHEIT
                else UnitOfTemperature.CELSIUS
            )
    return UnitOfTemperature.CELSIUS


SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    # Common
    "battery_level": EcoflowSensorEntityDescription(
        key="battery_level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "battery_level_main": SensorEntityDescription(
        key="battery_level_main",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "input_power": SensorEntityDescription(
        key="input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "output_power": SensorEntityDescription(
        key="output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "remaining_time_charging": SensorEntityDescription(
        key="remaining_time_charging",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
    ),
    "remaining_time_discharging": SensorEntityDescription(
        key="remaining_time_discharging",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
    ),
    # SHP2
    "grid_power": SensorEntityDescription(
        key="grid_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "in_use_power": SensorEntityDescription(
        key="in_use_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    **{
        f"circuit_power_{i}": SensorEntityDescription(
            key=f"circuit_power_{i}",
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            translation_key="circuit_power",
            translation_placeholders={"index": f"{i:02}"},
        )
        for i in range(1, shp2.Device.NUM_OF_CIRCUITS + 1)
    },
    **{
        f"circuit_current_{i}": SensorEntityDescription(
            key=f"circuit_current_{i}",
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            suggested_display_precision=2,
            entity_registry_enabled_default=False,
            translation_key="circuit_current",
            translation_placeholders={"index": f"{i:02}"},
        )
        for i in range(1, shp2.Device.NUM_OF_CIRCUITS + 1)
    },
    **{
        f"channel_power_{i}": SensorEntityDescription(
            key=f"channel_power_{i}",
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            suggested_display_precision=2,
            translation_key="channel_power",
            translation_placeholders={"index": f"{i:02}"},
        )
        for i in range(1, shp2.Device.NUM_OF_CHANNELS + 1)
    },
    # SHP2 Backup Channel Info - dynamically generated
    **_create_shp2_backup_channel_sensors(),
    # SHP2 Energy Info - dynamically generated
    **_create_shp2_channel_sensors(),
    # DPU
    **{
        f"{sensor}_{measurement}": SensorEntityDescription(
            key=f"{sensor}_{measurement}",
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key=f"port_{measurement}",
            translation_placeholders={"name": _auto_name_from_key(sensor)},
            suggested_display_precision=2,
        )
        for measurement, sensor in itertools.product(
            ["power"],
            [
                "lv_solar",
                "hv_solar",
                "ac_l1_1_out",
                "ac_l1_2_out",
                "ac_l2_1_out",
                "ac_l2_2_out",
                "ac_l14_out",
                "ac_tt_out",
                "ac_5p8_out",
            ],
        )
    },
    **{
        f"battery_{i}_battery_level": SensorEntityDescription(
            key=f"battery_{i}_battery_level",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="additional_battery_level",
            translation_placeholders={"index": f"{i}"},
            entity_registry_enabled_default=False,
        )
        for i in range(1, 6)
    },
    **{
        f"battery_{i}_cell_temperature": SensorEntityDescription(
            key=f"battery_{i}_cell_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="additional_battery_temperature",
            translation_placeholders={"index": f"{i}"},
            entity_registry_enabled_default=False,
        )
        for i in range(1, 6)
    },
    # River 3, Delta 3
    "input_energy": SensorEntityDescription(
        key="input_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "output_energy": SensorEntityDescription(
        key="output_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "ac_input_power": SensorEntityDescription(
        key="ac_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "ac_input_voltage": SensorEntityDescription(
        key="ac_input_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    "ac_input_current": SensorEntityDescription(
        key="ac_input_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    "ac_output_power": SensorEntityDescription(
        key="ac_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "ac_input_energy": SensorEntityDescription(
        key="ac_input_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "ac_output_energy": SensorEntityDescription(
        key="ac_output_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "dc_input_power": SensorEntityDescription(
        key="dc_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "dc_input_energy": SensorEntityDescription(
        key="dc_input_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "dc_output_power": SensorEntityDescription(
        key="dc_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "dc12v_output_power": SensorEntityDescription(
        key="dc12v_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "dc12v_output_energy": SensorEntityDescription(
        key="dc12v_output_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "usbc_output_power": SensorEntityDescription(
        key="usbc_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "usbc_output_energy": SensorEntityDescription(
        key="usbc_output_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "usba_output_power": SensorEntityDescription(
        key="usba_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "usba_output_energy": SensorEntityDescription(
        key="usba_output_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    "usbc2_output_power": SensorEntityDescription(
        key="usbc2_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "usbc3_output_power": SensorEntityDescription(
        key="usbc2_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "usba2_output_power": SensorEntityDescription(
        key="usba2_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "qc_usb1_output_power": SensorEntityDescription(
        key="qc_usb1_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "qc_usb2_output_power": SensorEntityDescription(
        key="qc_usb2_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "battery_input_power": SensorEntityDescription(
        key="battery_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "battery_output_power": SensorEntityDescription(
        key="battery_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "cell_temperature": SensorEntityDescription(
        key="cell_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
    ),
    "dc_port_input_power": SensorEntityDescription(
        key="dc_port_input_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=2,
    ),
    "dc_port_2_input_power": SensorEntityDescription(
        key="dc_port_input_power_2",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=2,
    ),
    "dc_port_state": SensorEntityDescription(
        key="dc_port_state",
        device_class=SensorDeviceClass.ENUM,
        options=_delta3_base.DCPortState.options(),
    ),
    "dc_port_2_state": SensorEntityDescription(
        key="dc_port_2_state",
        device_class=SensorDeviceClass.ENUM,
        options=_delta3_base.DCPortState.options(),
    ),
    "solar_input_power": SensorEntityDescription(
        key="input_power_solar",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "solar_input_power_2": SensorEntityDescription(
        key="input_power_solar_2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # DP3
    "ac_lv_output_power": SensorEntityDescription(
        key="ac_lv_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "ac_hv_output_power": SensorEntityDescription(
        key="ac_hv_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "solar_lv_power": SensorEntityDescription(
        key="input_power_solar_lv",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "solar_hv_power": SensorEntityDescription(
        key="input_power_solar_hv",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "dc_lv_input_power": SensorEntityDescription(
        key="dc_lv_input_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=2,
    ),
    "dc_hv_input_power": SensorEntityDescription(
        key="dc_hv_input_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=2,
    ),
    "dc_lv_input_state": SensorEntityDescription(
        key="dc_lv_input_state",
        device_class=SensorDeviceClass.ENUM,
        options=delta_pro_3.DCPortState.options(),
    ),
    "dc_hv_input_state": SensorEntityDescription(
        key="dc_hv_input_state",
        device_class=SensorDeviceClass.ENUM,
        options=delta_pro_3.DCPortState.options(),
    ),
    # Smart Generator
    "xt150_battery_level": SensorEntityDescription(
        key="xt150_battery_level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "engine_state": SensorEntityDescription(
        key="engine_state",
        device_class=SensorDeviceClass.ENUM,
        options=smart_generator.EngineOpen.options(),
    ),
    "liquefied_gas_type": SensorEntityDescription(
        key="liquefied_gas_type",
        device_class=SensorDeviceClass.ENUM,
        options=smart_generator.LiquefiedGasType.options(),
    ),
    "liquefied_gas_consumption": EcoflowSensorEntityDescription[smart_generator.Device](
        key="liquefied_gas_consumption",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "liquefied_gas_remaining": EcoflowSensorEntityDescription[smart_generator.Device](
        key="liquefied_gas_remaining",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "generator_abnormal_state": SensorEntityDescription(
        key="generator_abnormal_state",
        device_class=SensorDeviceClass.ENUM,
        options=smart_generator.AbnormalState.options(),
    ),
    "sub_battery_soc": SensorEntityDescription(
        key="sub_battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "sub_battery_state": SensorEntityDescription(
        key="sub_battery_state",
        device_class=SensorDeviceClass.ENUM,
        options=smart_generator.SubBatteryState.options(),
    ),
    "fuel_type": SensorEntityDescription(
        key="fuel_type",
        device_class=SensorDeviceClass.ENUM,
    ),
    # Alternator Charger
    "battery_temperature": SensorEntityDescription(
        key="battery_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "car_battery_voltage": SensorEntityDescription(
        key="car_battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "dc_power": SensorEntityDescription(
        key="dc_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # STREAM
    "grid_voltage": SensorEntityDescription(
        key="grid_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "grid_frequency": SensorEntityDescription(
        key="grid_frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "grid_current": SensorEntityDescription(
        key="grid_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "load_from_battery": SensorEntityDescription(
        key="load_from_battery",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "load_from_grid": SensorEntityDescription(
        key="load_from_grid",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "load_from_pv": SensorEntityDescription(
        key="load_from_pv",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    **{
        f"ac_power_{i}": SensorEntityDescription(
            key=f"ac_power_{i}",
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="port_power",
            translation_placeholders={"name": f"AC ({i})"},
        )
        for i in range(3)
    },
    **{
        f"pv_power_{i}": SensorEntityDescription(
            key=f"pv_power_{i}",
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            translation_key="port_power",
            translation_placeholders={"name": f"PV ({i})"},
        )
        for i in range(5)
    },
    "pv_power_sum": SensorEntityDescription(
        key="pv_power_sum",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        translation_key="pv_power_sum",
    ),
    # Smart Meter
    "grid_energy": SensorEntityDescription(
        key="grid_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    **{
        f"l{i}_power": SensorEntityDescription(
            key=f"l{i}_power",
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="port_power",
            translation_placeholders={"name": f"L{i}"},
            entity_registry_enabled_default=False,
        )
        for i in range(4)
    },
    **{
        f"l{i}_current": SensorEntityDescription(
            key=f"l{i}_current",
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="port_current",
            translation_placeholders={"name": f"L{i}"},
            entity_registry_enabled_default=False,
        )
        for i in range(4)
    },
    **{
        f"l{i}_voltage": SensorEntityDescription(
            key=f"l{i}_voltage",
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="port_voltage",
            translation_placeholders={"name": f"L{i}"},
            entity_registry_enabled_default=False,
        )
        for i in range(4)
    },
    **{
        f"l{i}_energy": SensorEntityDescription(
            key=f"l{i}_energy",
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=3,
            translation_key="port_energy",
            translation_placeholders={"name": f"L{i}"},
            entity_registry_enabled_default=False,
        )
        for i in range(4)
    },
    # Wave 3
    "ambient_temperature": EcoflowSensorEntityDescription[wave3.Device](
        key="ambient_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement_field=_wave_unit,
    ),
    "ambient_humidity": SensorEntityDescription(
        key="ambient_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    "operating_mode": SensorEntityDescription(
        key="operating_mode",
        device_class=SensorDeviceClass.ENUM,
        options=wave3.OperatingMode.options(),
    ),
    "condensate_water_level": SensorEntityDescription(
        key="condensate_water_level",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    "sleep_state": SensorEntityDescription(
        key="sleep_state",
        device_class=SensorDeviceClass.ENUM,
        options=wave3.SleepState.options(),
    ),
    "pcs_fan_level": SensorEntityDescription(
        key="pcs_fan_level",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    "in_drainage": SensorEntityDescription(
        key="in_drainage",
    ),
    "drainage_mode": SensorEntityDescription(
        key="drainage_mode",
    ),
    "lcd_show_temp_type": SensorEntityDescription(
        key="lcd_show_temp_type",
    ),
    "temp_indoor_supply_air": EcoflowSensorEntityDescription(
        key="temp_indoor_supply_air",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement_field=_wave_unit,
    ),
    "temp_indoor_return_air": EcoflowSensorEntityDescription(
        key="temp_indoor_return_air",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement_field=_wave_unit,
    ),
    "temp_outdoor_ambient": EcoflowSensorEntityDescription(
        key="temp_outdoor_ambient",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement_field=_wave_unit,
    ),
    "temp_condenser": EcoflowSensorEntityDescription(
        key="temp_condenser",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement_field=_wave_unit,
    ),
    "temp_evaporator": EcoflowSensorEntityDescription(
        key="temp_evaporator",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement_field=_wave_unit,
    ),
    "temp_compressor_discharge": EcoflowSensorEntityDescription(
        key="temp_compressor_discharge",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement_field=_wave_unit,
    ),
    # Delta 2
    "dc12v_output_voltage": SensorEntityDescription(
        key="dc12v_output_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    "dc12v_output_current": SensorEntityDescription(
        key="dc12v_output_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    # Wave 2
    "outlet_temperature": SensorEntityDescription(
        key="outlet_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    "power_battery": SensorEntityDescription(
        key="power_battery",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "power_psdr": SensorEntityDescription(
        key="power_psdr",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "power_mppt": SensorEntityDescription(
        key="power_mppt",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "water_level": SensorEntityDescription(
        key="water_level",
        device_class=SensorDeviceClass.ENUM,
        options=wave2.WaterLevel.options(),
    ),
    # unsupported
    "collecting_data": SensorEntityDescription(
        key="collecting_data",
        name="Collecting data",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    **{
        f"pv_current_{i}": SensorEntityDescription(
            key=f"pv_current_{i}",
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            translation_key="port_current",
            translation_placeholders={"name": f"PV ({i})"},
        )
        for i in range(1, 3)
    },
    **{
        f"pv_voltage_{i}": SensorEntityDescription(
            key=f"pv_voltage_{i}",
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            translation_key="port_voltage",
            translation_placeholders={"name": f"PV ({i})"},
        )
        for i in range(1, 3)
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    device = config_entry.runtime_data

    new_sensors = [
        EcoflowSensor(device, sensor)
        for sensor in SENSOR_TYPES
        if hasattr(device, sensor)
    ]

    if new_sensors:
        async_add_entities(new_sensors)


class EcoflowSensor(EcoflowEntity, SensorEntity):
    """Base representation of a sensor."""

    def __init__(self, device: DeviceBase, sensor: str):
        """Initialize the sensor."""
        super().__init__(device)

        self._sensor = sensor
        self._attr_unique_id = f"{device.name}_{sensor}"

        if sensor in SENSOR_TYPES:
            self.entity_description = SENSOR_TYPES[sensor]
            if self.entity_description.translation_key is None:
                self._attr_translation_key = self.entity_description.key

        self._attribute_fields = (
            self.entity_description.state_attribute_fields
            if isinstance(self.entity_description, EcoflowSensorEntityDescription)
            else []
        )

    @property
    def native_value(self):
        """Return the value of the sensor."""
        value = getattr(self._device, self._sensor, None)
        if isinstance(value, Enum):
            return value.name.lower()
        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        if isinstance(self.entity_description, EcoflowSensorEntityDescription):
            unit = self.entity_description.native_unit_of_measurement_field
            match unit:
                case str():
                    return getattr(self._device, unit)
                case Callable():
                    return unit(self._device)
        return self.entity_description.native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._attribute_fields:
            return {}

        return {
            field_name: getattr(self._device, field_name)
            for field_name in self._attribute_fields
            if hasattr(self._device, field_name)
        }

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""
        await super().async_added_to_hass()
        self._device.register_callback(self.async_write_ha_state, self._sensor)

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        await super().async_will_remove_from_hass()
        self._device.remove_callback(self.async_write_ha_state, self._sensor)

"""EcoFlow BLE sensor"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum, EnumType
from typing import Any, Final, TypedDict, Unpack

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfMass,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceConfigEntry
from .const import CONF_EXTRA_BATTERY, DOMAIN
from .eflib import DeviceBase
from .eflib.devices import (
    _delta3_base,
    delta_pro_3,
    dpu,
    powerpulse_ev,
    shp2,
    smart_generator,
    stream_microinverter,
    wave2,
    wave3,
)
from .eflib.props.enums import IntFieldValue
from .entity import (
    EcoflowBatteryAddonEntity,
    EcoflowEntity,
    resolve_entity_description_keys,
)


@dataclass(frozen=True, kw_only=True)
class EcoflowSensorEntityDescription[Device: DeviceBase](SensorEntityDescription):
    state_attribute_fields: list[str] = field(default_factory=list)
    native_unit_of_measurement_field: str | Callable[[Device], str] | None = None
    indexed_range: range | None = None


class _SensorKwargs(TypedDict, total=False):
    translation_key: str
    translation_placeholders: dict[str, str]
    indexed_range: range
    entity_category: EntityCategory
    state_attribute_fields: list[str]


def battery(
    key: str = "", enabled: bool = True, **kwargs: Unpack[_SensorKwargs]
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def power(
    key: str = "",
    *,
    enabled: bool = True,
    precision: int | None = None,
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=state_class,
        suggested_display_precision=precision,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def power_factor(
    key: str = "",
    *,
    enabled: bool = False,
    precision: int | None = 0,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=precision,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def energy(
    key: str = "", enabled: bool = True, **kwargs: Unpack[_SensorKwargs]
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def energy_storage(
    key: str = "", enabled: bool = True, **kwargs: Unpack[_SensorKwargs]
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def voltage(
    key: str = "",
    *,
    enabled: bool = True,
    precision: int | None = None,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=precision,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def current(
    key: str = "",
    *,
    enabled: bool = True,
    precision: int | None = None,
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=state_class,
        suggested_display_precision=precision,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def temperature(
    key: str = "", enabled: bool = True, **kwargs: Unpack[_SensorKwargs]
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def _wave_unit(dev: wave3.Device):
    match dev:
        case wave3.Device:
            return (
                UnitOfTemperature.FAHRENHEIT
                if dev.temp_unit is wave3.TemperatureUnit.FAHRENHEIT
                else UnitOfTemperature.CELSIUS
            )
    return UnitOfTemperature.CELSIUS


def wave_temperature(
    key: str = "", enabled: bool = True, **kwargs: Unpack[_SensorKwargs]
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement_field=_wave_unit,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def duration(
    key: str = "", enabled: bool = True, **kwargs: Unpack[_SensorKwargs]
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def frequency(
    key: str = "",
    *,
    enabled: bool = True,
    precision: int | None = None,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=precision,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def _liquefied_gas_unit(dev: DeviceBase) -> str:
    unit = getattr(dev, "liquefied_gas_unit", None)
    if (
        unit is not None
        and getattr(unit, "value", -1) == smart_generator.LiquefiedGasUnit.LB.value
    ):
        return UnitOfMass.POUNDS
    return UnitOfMass.KILOGRAMS


def weight(
    key: str = "",
    enabled: bool = True,
    unit: str | None = UnitOfMass.KILOGRAMS,
    unit_field: "str | Callable[[DeviceBase], str] | None" = None,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None if unit_field is not None else unit,
        native_unit_of_measurement_field=unit_field,
        suggested_display_precision=2,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def humidity(
    key: str = "", enabled: bool = True, **kwargs: Unpack[_SensorKwargs]
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def percentage(
    key: str = "", enabled: bool = True, **kwargs: Unpack[_SensorKwargs]
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def enum(
    key: str = "",
    enabled: bool = True,
    options: list[str] | type[IntFieldValue] | None = None,
    name: str | None = None,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    if type(options) is EnumType and issubclass(options, IntFieldValue):
        options = options.options()

    return EcoflowSensorEntityDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.ENUM,
        options=options,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def raw(
    key: str = "",
    enabled: bool = True,
    state_class: SensorStateClass | None = None,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        state_class=state_class,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def port_power(
    name: str,
    *,
    enabled: bool = True,
    precision: int | None = None,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return power(
        enabled=enabled,
        precision=precision,
        translation_key="port_power",
        translation_placeholders={"name": name},
        **kwargs,
    )


def port_voltage(
    name: str,
    *,
    enabled: bool = False,
    precision: int | None = 2,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return voltage(
        enabled=enabled,
        precision=precision,
        translation_key="port_voltage",
        translation_placeholders={"name": name},
        entity_category=EntityCategory.DIAGNOSTIC,
        **kwargs,
    )


def port_current(
    name: str,
    *,
    enabled: bool = False,
    precision: int | None = 2,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return current(
        enabled=enabled,
        precision=precision,
        translation_key="port_current",
        translation_placeholders={"name": name},
        entity_category=EntityCategory.DIAGNOSTIC,
        **kwargs,
    )


def port_temperature(
    name: str,
    *,
    enabled: bool = False,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return temperature(
        enabled=enabled,
        translation_key="port_temperature",
        translation_placeholders={"name": name},
        entity_category=EntityCategory.DIAGNOSTIC,
        **kwargs,
    )


def port_power_factor(
    name: str,
    *,
    enabled: bool = False,
    precision: int | None = 0,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return power_factor(
        enabled=enabled,
        precision=precision,
        translation_key="port_power_factor",
        translation_placeholders={"name": name},
        **kwargs,
    )


def port_error_code(
    name: str,
    *,
    enabled: bool = False,
    **kwargs: Unpack[_SensorKwargs],
) -> EcoflowSensorEntityDescription:
    return raw(
        enabled=enabled,
        translation_key="port_error_code",
        translation_placeholders={"name": name},
        entity_category=EntityCategory.DIAGNOSTIC,
        **kwargs,
    )


_shp2_circuit_range = range(1, shp2.Device.NUM_OF_CIRCUITS + 1)
_shp2_channel_range = range(1, shp2.Device.NUM_OF_CHANNELS + 1)


def shp2_channel(
    fn: Callable[..., EcoflowSensorEntityDescription],
    translation_key: str | None = None,
    translation_placeholders: dict[str, str] | None = None,
    **kwargs,
) -> EcoflowSensorEntityDescription:
    return fn(
        translation_key=translation_key,
        translation_placeholders=translation_placeholders or {"channel": "{n}"},
        indexed_range=_shp2_channel_range,
        **kwargs,
    )


def shp2_circuit(
    fn: Callable[..., EcoflowSensorEntityDescription],
    translation_key: str | None = None,
    translation_placeholders: dict[str, str] | None = None,
    **kwargs,
) -> EcoflowSensorEntityDescription:
    return fn(
        translation_key=translation_key,
        translation_placeholders=translation_placeholders or {"index": "{n:02d}"},
        indexed_range=_shp2_circuit_range,
        **kwargs,
    )


_SENSORS: Final[dict[str, SensorEntityDescription]] = {
    # Common
    "battery_level": battery(),
    "battery_level_main": battery(),
    "input_power": power(precision=0),
    "output_power": power(precision=0),
    "remaining_time_charging": duration(enabled=False),
    "remaining_time_discharging": duration(enabled=False),
    "total_energy": energy(),
    # SHP2
    "grid_power": power(precision=1),
    "power_status": enum(options=shp2.PowerStatus),
    "in_use_power": power(precision=2),
    "circuit_power_{n}": shp2_circuit(
        power,
        "circuit_power",
        precision=2,
        translation_placeholders={"index": "{n:02d}"},
    ),
    "circuit_current_{n}": shp2_circuit(
        current, "circuit_current", precision=2, enabled=False, state_class=None
    ),
    "channel_power_{n}": shp2_channel(
        power,
        "channel_power",
        precision=2,
        state_class=None,
        translation_placeholders={"index": "{n}"},
    ),
    # SHP2 ch info (backup channel)
    "ch{n}_ctrl_status": shp2_channel(
        enum,
        "backup_ctrl_status",
        options=shp2.ControlStatus,
    ),
    "ch{n}_backup_rly1_cnt": shp2_channel(
        raw,
        "backup_relay1_count",
        enabled=False,
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "ch{n}_backup_rly2_cnt": shp2_channel(
        raw,
        "backup_relay2_count",
        enabled=False,
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "ch{n}_wake_up_charge_status": shp2_channel(
        battery,
        "backup_wakeup_charge",
        enabled=False,
    ),
    "ch{n}_5p8_type": shp2_channel(
        raw,
        "backup_connector_type",
        enabled=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # SHP2 energy info (per-channel)
    "channel{n}_sn": shp2_channel(
        raw,
        "channel_serial_number",
        enabled=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "channel{n}_type": shp2_channel(
        raw,
        "channel_device_type",
        enabled=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "channel{n}_capacity": shp2_channel(
        energy_storage,
        "channel_full_capacity",
        enabled=False,
    ),
    "channel{n}_rate_power": shp2_channel(
        power,
        "channel_rated_power",
        precision=0,
        enabled=False,
    ),
    "channel{n}_battery_percentage": shp2_channel(
        battery,
        "channel_battery_level",
    ),
    "channel{n}_output_power": shp2_channel(
        power,
        "channel_output_power",
        precision=1,
    ),
    "channel{n}_battery_temp": shp2_channel(
        temperature,
        "channel_battery_temperature",
    ),
    "channel{n}_lcd_input": shp2_channel(
        power,
        "channel_lcd_input_power",
        precision=0,
        enabled=False,
    ),
    "channel{n}_pv_status": shp2_channel(
        enum, "channel_pv_status", enabled=False, options=shp2.PVStatus
    ),
    "channel{n}_pv_lv_input": shp2_channel(
        power,
        "channel_pv_lv_input_power",
        precision=0,
    ),
    "channel{n}_pv_hv_input": shp2_channel(
        power,
        "channel_pv_hv_input_power",
        precision=0,
    ),
    "channel{n}_error_code": shp2_channel(
        raw,
        "channel_error_count",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # DPU
    "lv_solar_power": port_power("LV Solar", precision=2),
    "lv_solar_voltage": port_voltage("LV Solar"),
    "lv_solar_current": port_current("LV Solar"),
    "lv_solar_temperature": port_temperature("LV Solar"),
    "lv_solar_error_code": port_error_code("LV Solar"),
    "hv_solar_power": port_power("HV Solar", precision=2),
    "hv_solar_voltage": port_voltage("HV Solar"),
    "hv_solar_current": port_current("HV Solar"),
    "hv_solar_temperature": port_temperature("HV Solar"),
    "hv_solar_error_code": port_error_code("HV Solar"),
    "ac_5p8_in_power": port_power("AC 5P8 In", precision=2),
    "ac_5p8_in_voltage": port_voltage("AC 5P8 In"),
    "ac_5p8_in_current": port_current("AC 5P8 In"),
    "ac_5p8_in_type": enum(
        key="ac_5p8_in_type",
        enabled=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=dpu.Access5p8InputType,
    ),
    "ac_c20_in_power": port_power("AC C20 In", precision=2),
    "ac_c20_in_voltage": port_voltage("AC C20 In"),
    "ac_c20_in_current": port_current("AC C20 In"),
    "ac_c20_in_type": raw(
        key="ac_c20_in_type",
        enabled=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "usb1_out_power": port_power("USB (1) Out", precision=2),
    "usb1_out_voltage": port_voltage("USB (1) Out"),
    "usb1_out_current": port_current("USB (1) Out"),
    "usb2_out_power": port_power("USB (2) Out", precision=2),
    "usb2_out_voltage": port_voltage("USB (2) Out"),
    "usb2_out_current": port_current("USB (2) Out"),
    "typec1_out_power": port_power("USB-C (1) Out", precision=2),
    "typec1_out_voltage": port_voltage("USB-C (1) Out"),
    "typec1_out_current": port_current("USB-C (1) Out"),
    "typec2_out_power": port_power("USB-C (2) Out", precision=2),
    "typec2_out_voltage": port_voltage("USB-C (2) Out"),
    "typec2_out_current": port_current("USB-C (2) Out"),
    "anderson_out_power": port_power("Anderson Out", precision=2),
    "anderson_out_voltage": port_voltage("Anderson Out"),
    "anderson_out_current": port_current("Anderson Out"),
    "anderson_out_error_code": port_error_code("Anderson Out"),
    "ac_l1_1_out_power": port_power("AC L1 (1) Out", precision=2),
    "ac_l1_1_out_voltage": port_voltage("AC L1 (1) Out"),
    "ac_l1_1_out_current": port_current("AC L1 (1) Out"),
    "ac_l1_1_out_power_factor": port_power_factor("AC L1 (1) Out"),
    "ac_l1_2_out_power": port_power("AC L1 (2) Out", precision=2),
    "ac_l1_2_out_voltage": port_voltage("AC L1 (2) Out"),
    "ac_l1_2_out_current": port_current("AC L1 (2) Out"),
    "ac_l1_2_out_power_factor": port_power_factor("AC L1 (2) Out"),
    "ac_l2_1_out_power": port_power("AC L2 (1) Out", precision=2),
    "ac_l2_1_out_voltage": port_voltage("AC L2 (1) Out"),
    "ac_l2_1_out_current": port_current("AC L2 (1) Out"),
    "ac_l2_1_out_power_factor": port_power_factor("AC L2 (1) Out"),
    "ac_l2_2_out_power": port_power("AC L2 (2) Out", precision=2),
    "ac_l2_2_out_voltage": port_voltage("AC L2 (2) Out"),
    "ac_l2_2_out_current": port_current("AC L2 (2) Out"),
    "ac_l2_2_out_power_factor": port_power_factor("AC L2 (2) Out"),
    "ac_tt_out_power": port_power("AC TT Out", precision=2),
    "ac_tt_out_voltage": port_voltage("AC TT Out"),
    "ac_tt_out_current": port_current("AC TT Out"),
    "ac_tt_out_power_factor": port_power_factor("AC TT Out"),
    "ac_l14_out_power": port_power("AC L14 Out", precision=2),
    "ac_l14_out_voltage": port_voltage("AC L14 Out"),
    "ac_l14_out_current": port_current("AC L14 Out"),
    "ac_l14_out_power_factor": port_power_factor("AC L14 Out"),
    "ac_5p8_out_power": port_power("AC 5P8 Out", precision=2),
    "ac_5p8_out_voltage": port_voltage("AC 5P8 Out"),
    "ac_5p8_out_current": port_current("AC 5P8 Out"),
    "ac_5p8_out_power_factor": port_power_factor("AC 5P8 Out"),
    "ac_5p8_out_type": enum(
        key="ac_5p8_out_type",
        enabled=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=dpu.Access5p8OutputType,
    ),
    "battery_voltage": port_voltage("Battery"),
    "battery_current": port_current("Battery"),
    "dc_inverter_temperature": port_temperature("DC Inverter"),
    "dc_inverter_error_code": port_error_code("DC Inverter"),
    "ac_inverter_temperature": port_temperature("AC Inverter"),
    "ac_inverter_error_code": port_error_code("AC Inverter"),
    "system_temperature": port_temperature("System"),
    # River 3, Delta 3
    "input_energy": energy(),
    "output_energy": energy(),
    "ac_input_power": power(precision=2),
    "ac_input_voltage": voltage(precision=1, enabled=False),
    "ac_input_current": current(precision=2, enabled=False),
    "ac_output_power": power(precision=2),
    "ac_output_voltage": voltage(precision=2, enabled=False),
    "ac_output_current": current(precision=2, enabled=False),
    "ac_input_energy": energy(),
    "ac_output_energy": energy(),
    "dc_input_power": power(precision=2),
    "dc_input_energy": energy(),
    "dc_output_power": power(precision=2),
    "dc12v_output_power": power(precision=2),
    "dc12v_output_energy": energy(),
    "usba_output_power": power(),
    "usba_output_energy": energy(),
    "usba2_output_power": power(),
    "usbc_output_power": power(),
    "usbc_output_energy": energy(),
    "usbc2_output_power": power(),
    "usbc3_output_power": power(),
    "qc_usb1_output_power": power(),
    "qc_usb2_output_power": power(),
    "battery_input_power": power(enabled=False),
    "battery_output_power": power(enabled=False),
    "cell_temperature": temperature(enabled=False),
    "dc_port_input_power": power(precision=2),
    "dc_port_2_input_power": power("dc_port_input_power_2", precision=2),
    "dc_port_state": enum(options=_delta3_base.DCPortState),
    "dc_port_2_state": enum(options=_delta3_base.DCPortState),
    "solar_input_power": power("input_power_solar", enabled=False),
    "solar_input_power_2": power("input_power_solar_2", enabled=False),
    # DP3
    "ac_lv_output_power": power(precision=2),
    "ac_hv_output_power": power(precision=2),
    "solar_lv_power": power("input_power_solar_lv", enabled=False),
    "solar_hv_power": power("input_power_solar_hv", enabled=False),
    "dc_lv_input_power": power(precision=2),
    "dc_hv_input_power": power(precision=2),
    "dc_lv_input_state": enum(options=delta_pro_3.DCPortState),
    "dc_hv_input_state": enum(options=delta_pro_3.DCPortState),
    # Smart Generator
    "xt150_battery_level": battery(),
    "engine_state": enum(options=smart_generator.EngineOpen),
    "liquefied_gas_type": enum(options=smart_generator.LiquefiedGasType),
    "liquefied_gas_consumption": weight(unit_field=_liquefied_gas_unit),
    "liquefied_gas_remaining": weight(unit_field=_liquefied_gas_unit),
    "generator_abnormal_state": enum(options=smart_generator.AbnormalState),
    "sub_battery_soc": battery(),
    "sub_battery_state": enum(options=smart_generator.SubBatteryState),
    "fuel_type": enum(),
    # Alternator Charger
    "battery_temperature": temperature(),
    "car_battery_voltage": voltage(),
    "dc_power": power(),
    # STREAM
    "grid_connection_status": enum(
        enabled=False,
        options=stream_microinverter.GridStatus,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "wifi_rssi": raw(
        enabled=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "grid_voltage": voltage(precision=1),
    "grid_frequency": frequency(precision=2),
    "grid_current": current(precision=2),
    "load_from_battery": power(),
    "load_from_grid": power(),
    "load_from_pv": power(),
    "ac_power_{n}": port_power("AC ({n})", indexed_range=range(3)),
    "ac_power_1_1": port_power("AC (1-1)"),
    "ac_power_1_2": port_power("AC (1-2)"),
    "ac_power_1_3": port_power("AC (1-3)"),
    "ac_power_2_1": port_power("AC (2-1)"),
    "ac_power_2_2": port_power("AC (2-2)"),
    "ac_power_2_3": port_power("AC (2-3)"),
    "pv_power_{n}": port_power("PV ({n})", precision=1, indexed_range=range(5)),
    "pv_power_sum": power(precision=1, translation_key="pv_power_sum"),
    # Smart Meter
    "grid_energy": energy(),
    "l{n}_power": port_power("L{n}", enabled=False, indexed_range=range(4)),
    "l{n}_current": current(
        enabled=False,
        translation_key="port_current",
        translation_placeholders={"name": "L{n}"},
        indexed_range=range(4),
    ),
    "l{n}_voltage": voltage(
        enabled=False,
        translation_key="port_voltage",
        translation_placeholders={"name": "L{n}"},
        indexed_range=range(4),
    ),
    "l{n}_energy": energy(
        enabled=False,
        translation_key="port_energy",
        translation_placeholders={"name": "L{n}"},
        indexed_range=range(4),
    ),
    # Wave 3
    "ambient_temperature": wave_temperature(),
    "ambient_humidity": humidity(),
    "operating_mode": enum(options=wave3.OperatingMode),
    "condensate_water_level": percentage(),
    "sleep_state": enum(options=wave3.SleepState),
    "pcs_fan_level": percentage(),
    "in_drainage": raw(),
    "drainage_mode": raw(),
    "lcd_show_temp_type": raw(),
    "temp_indoor_supply_air": wave_temperature(),
    "temp_indoor_return_air": wave_temperature(),
    "temp_outdoor_ambient": wave_temperature(),
    "temp_condenser": wave_temperature(),
    "temp_evaporator": wave_temperature(),
    "temp_compressor_discharge": wave_temperature(),
    # Delta 2
    "dc12v_output_voltage": voltage(precision=2, enabled=False),
    "dc12v_output_current": current(precision=2, enabled=False),
    "dc_input_voltage": voltage(precision=2, enabled=False),
    "dc_input_current": current(precision=2, enabled=False),
    "xt60_input_power": power(),
    "xt60_1_input_power": power(),
    "xt60_2_input_power": power(),
    "pv_current_{n}": current(
        precision=2,
        translation_key="port_current",
        translation_placeholders={"name": "PV ({n})"},
        indexed_range=range(1, 3),
    ),
    "pv_voltage_{n}": voltage(
        precision=1,
        translation_key="port_voltage",
        translation_placeholders={"name": "PV ({n})"},
        indexed_range=range(1, 3),
    ),
    # Wave 2
    "outlet_temperature": temperature(),
    "power_battery": power(precision=0),
    "power_psdr": power(precision=0),
    "power_mppt": power(precision=0),
    "water_level": enum(options=wave2.WaterLevel),
    # PowerStream
    "battery_power": power(precision=1),
    "inverter_temperature": temperature(),
    "inverter_current": current(precision=2),
    "inverter_power": power(precision=0),
    "inverter_voltage": voltage(precision=1),
    "inverter_frequency": frequency(precision=1),
    "pv_temperature_{n}": temperature(
        translation_key="port_temperature",
        translation_placeholders={"name": "PV ({n})"},
        indexed_range=range(1, 3),
    ),
    "llc_temperature": temperature(),
    # PowerPulse EV
    "ac_plug_state": enum(options=powerpulse_ev.AcPlugState),
    # unsupported
    "collecting_data": enum(
        name="Collecting data",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

SENSOR_TYPES: Final[dict[str, SensorEntityDescription]] = (
    resolve_entity_description_keys(_SENSORS)
)


_BATTERY_ADDON_SENSORS: Final = {
    "battery_{n}_battery_level": battery(translation_key="battery_level"),
    "battery_{n}_cell_temperature": temperature(translation_key="cell_temperature"),
    "battery_{n}_input_power": power(precision=0, translation_key="input_power"),
    "battery_{n}_output_power": power(precision=0, translation_key="output_power"),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
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

    if battery_entities := _get_extra_battery_entities(
        hass=hass, device=device, conf=config_entry.data.get(CONF_EXTRA_BATTERY)
    ):
        async_add_entities(battery_entities)


def _get_extra_battery_entities(
    hass: HomeAssistant, device: DeviceBase, conf: list[str] | None
):
    available_indices = [
        i for i in range(1, 6) if hasattr(device, f"battery_{i}_battery_level")
    ]

    if not available_indices:
        return []

    if conf is not None:
        enabled_indices = {int(i) for i in conf}
    else:
        enabled_indices = {
            i
            for i in available_indices
            if getattr(device, f"battery_{i}_enabled", False)
        }

    registry = dr.async_get(hass)
    for battery_index in available_indices:
        if battery_index not in enabled_indices:
            identifier = (DOMAIN, f"{device.address}_battery_{battery_index}")
            if dev_entry := registry.async_get_device(identifiers={identifier}):
                registry.async_remove_device(dev_entry.id)

    battery_entities: list[EcoflowBatteryAddonSensor] = []
    for battery_index in enabled_indices:
        if battery_index not in available_indices:
            continue

        for template_key, desc in _BATTERY_ADDON_SENSORS.items():
            attr_name = template_key.replace("{n}", str(battery_index))
            if not hasattr(device, attr_name):
                continue

            battery_entities.append(
                EcoflowBatteryAddonSensor(
                    device=device,
                    sensor=attr_name,
                    description=replace(desc, key=attr_name),
                    battery_index=battery_index,
                )
            )

    return battery_entities


class EcoflowSensor(EcoflowEntity, SensorEntity):
    """Base representation of a sensor."""

    def __init__(self, device: DeviceBase, sensor: str):
        """Initialize the sensor."""
        super().__init__(device)

        self._sensor = sensor
        self._attr_unique_id = f"ef_{device.serial_number}_{sensor}"

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


class EcoflowBatteryAddonSensor(EcoflowBatteryAddonEntity, SensorEntity):
    def __init__(
        self,
        device: DeviceBase,
        sensor: str,
        description: SensorEntityDescription,
        battery_index: int,
    ) -> None:
        super().__init__(device=device, battery_index=battery_index)
        self._sensor = sensor
        self._attr_unique_id = f"ef_{device.serial_number}_{description.key}"
        self._attr_native_value = getattr(device, sensor, None)
        self.entity_description = description
        if self.entity_description.translation_key is None:
            self._attr_translation_key = self.entity_description.key

    @property
    def native_value(self):
        return getattr(self._device, self._sensor, None)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._device.register_callback(self.async_write_ha_state, self._sensor)

    async def async_will_remove_from_hass(self):
        await super().async_will_remove_from_hass()
        self._device.remove_callback(self.async_write_ha_state, self._sensor)

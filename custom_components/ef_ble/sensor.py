"""EcoFlow BLE sensor"""

from collections.abc import Callable
from dataclasses import dataclass, field
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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceConfigEntry
from .const import CONF_EXTRA_BATTERY, DOMAIN
from .eflib import DeviceBase
from .eflib.devices import (
    _delta3_base,
    delta_pro_3,
    shp2,
    smart_generator,
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
    """Create an energy storage capacity sensor description."""
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


def weight(
    key: str = "", enabled: bool = True, **kwargs: Unpack[_SensorKwargs]
) -> EcoflowSensorEntityDescription:
    return EcoflowSensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
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


_shp2_circuit_range = range(1, shp2.Device.NUM_OF_CIRCUITS + 1)
_shp2_channel_range = range(1, shp2.Device.NUM_OF_CHANNELS + 1)


def shp2_channel(
    fn: Callable[..., EcoflowSensorEntityDescription],
    translation_key: str | None = None,
    **kwargs,
) -> EcoflowSensorEntityDescription:
    """Indexed SHP2 channel sensor with channel placeholder pre-filled."""
    return fn(
        translation_key=translation_key,
        translation_placeholders={"channel": "{n}"},
        indexed_range=_shp2_channel_range,
        **kwargs,
    )


def shp2_circuit(
    fn: Callable[..., EcoflowSensorEntityDescription],
    translation_key: str | None = None,
    **kwargs,
) -> EcoflowSensorEntityDescription:
    """Indexed SHP2 circuit sensor with zero-padded index placeholder pre-filled."""
    return fn(
        translation_key=translation_key,
        translation_placeholders={"index": "{n:02d}"},
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
    # SHP2
    "grid_power": power(precision=1),
    "in_use_power": power(precision=2),
    "circuit_power_{n}": shp2_circuit(power, "circuit_power", precision=2),
    "circuit_current_{n}": shp2_circuit(
        current, "circuit_current", precision=2, enabled=False, state_class=None
    ),
    "channel_power_{n}": power(
        precision=2,
        state_class=None,
        translation_key="channel_power",
        translation_placeholders={"index": "{n:02d}"},
        indexed_range=_shp2_channel_range,
    ),
    "ch{n}_ctrl_status": shp2_channel(
        enum, "backup_ctrl_status", options=shp2.ControlStatus
    ),
    "ch{n}_force_charge": shp2_channel(
        enum,
        "backup_force_charge",
        enabled=False,
        options=shp2.ForceChargeStatus.options(include_unknown=False),
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
        battery, "backup_wakeup_charge", enabled=False
    ),
    "ch{n}_5p8_type": shp2_channel(
        raw,
        "backup_connector_type",
        enabled=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
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
        energy_storage, "channel_full_capacity", enabled=False
    ),
    "channel{n}_rate_power": shp2_channel(
        power, "channel_rated_power", precision=0, enabled=False
    ),
    "channel{n}_battery_percentage": shp2_channel(battery, "channel_battery_level"),
    "channel{n}_output_power": shp2_channel(power, "channel_output_power", precision=1),
    "channel{n}_battery_temp": shp2_channel(temperature, "channel_battery_temperature"),
    "channel{n}_lcd_input": shp2_channel(
        power, "channel_lcd_input_power", precision=0, enabled=False
    ),
    "channel{n}_pv_status": shp2_channel(
        enum,
        "channel_pv_status",
        enabled=False,
        options=shp2.PVStatus.options(include_unknown=False),
    ),
    "channel{n}_pv_lv_input": shp2_channel(
        power, "channel_pv_lv_input_power", precision=0
    ),
    "channel{n}_pv_hv_input": shp2_channel(
        power, "channel_pv_hv_input_power", precision=0
    ),
    "channel{n}_error_code": shp2_channel(
        raw,
        "channel_error_count",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # DPU
    "lv_solar_power": port_power("LV Solar", precision=2),
    "hv_solar_power": port_power("HV Solar", precision=2),
    "ac_l1_1_out_power": port_power("AC L1 1 Out", precision=2),
    "ac_l1_2_out_power": port_power("AC L1 2 Out", precision=2),
    "ac_l2_1_out_power": port_power("AC L2 1 Out", precision=2),
    "ac_l2_2_out_power": port_power("AC L2 2 Out", precision=2),
    "ac_l14_out_power": port_power("AC L14 Out", precision=2),
    "ac_tt_out_power": port_power("AC TT Out", precision=2),
    "ac_5p8_out_power": port_power("AC 5P8 Out", precision=2),
    # River 3, Delta 3
    "input_energy": energy(),
    "output_energy": energy(),
    "ac_input_power": power(precision=2),
    "ac_input_voltage": voltage(precision=1, enabled=False),
    "ac_input_current": current(precision=2, enabled=False),
    "ac_output_power": power(precision=2),
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
    "liquefied_gas_consumption": weight(),
    "liquefied_gas_remaining": weight(),
    "generator_abnormal_state": enum(options=smart_generator.AbnormalState),
    "sub_battery_soc": battery(),
    "sub_battery_state": enum(options=smart_generator.SubBatteryState),
    "fuel_type": enum(),
    # Alternator Charger
    "battery_temperature": temperature(),
    "car_battery_voltage": voltage(),
    "dc_power": power(),
    # STREAM
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
    # unsupported
    "collecting_data": enum(
        name="Collecting data",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

SENSOR_TYPES: Final[dict[str, SensorEntityDescription]] = (
    resolve_entity_description_keys(_SENSORS, EcoflowSensorEntityDescription)
)


_BATTERY_ADDON_INDEX_SENSORS: Final = resolve_entity_description_keys(
    {
        "battery_{n}_battery_level": battery(translation_key="battery_level"),
        "battery_{n}_cell_temperature": temperature(translation_key="cell_temperature"),
        "battery_{n}_input_power": power(precision=0, translation_key="input_power"),
        "battery_{n}_output_power": power(precision=0, translation_key="output_power"),
    },
    EcoflowSensorEntityDescription,
)


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

        for template_key, desc in _BATTERY_ADDON_INDEX_SENSORS.items():
            attr_name = template_key.replace("{n}", str(battery_index))
            if not hasattr(device, attr_name):
                continue

            battery_entities.append(
                EcoflowBatteryAddonSensor(
                    device=device,
                    sensor=attr_name,
                    description=desc,
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
        self._attr_unique_id = f"ef_{device.serial_number}_{sensor}"
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

"""EcoFlow BLE binary sensor"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final, TypedDict, Unpack

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ef_ble.eflib import DeviceBase
from custom_components.ef_ble.eflib.devices import shp2

from . import DeviceConfigEntry
from .entity import EcoflowEntity, resolve_entity_description_keys


@dataclass(frozen=True, kw_only=True)
class EcoflowBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary sensor entity description with optional indexed expansion support."""

    update_state: Callable[[bool], None] | None = None
    indexed_range: range | None = None
    state_attribute_fields: list[str] = field(default_factory=list)


class _BinarySensorKwargs(TypedDict, total=False):
    translation_key: str
    translation_placeholders: dict[str, str]
    indexed_range: range
    entity_category: EntityCategory
    state_attribute_fields: list[str]


def _make_desc(
    device_class: BinarySensorDeviceClass,
    key: str = "",
    *,
    enabled: bool = True,
    **kwargs: Unpack[_BinarySensorKwargs],
) -> EcoflowBinarySensorEntityDescription:
    return EcoflowBinarySensorEntityDescription(
        key=key,
        device_class=device_class,
        entity_registry_enabled_default=enabled,
        **kwargs,
    )


def lock(
    key: str = "", *, enabled: bool = True, **kwargs: Unpack[_BinarySensorKwargs]
) -> EcoflowBinarySensorEntityDescription:
    return _make_desc(BinarySensorDeviceClass.LOCK, key, enabled=enabled, **kwargs)


def problem(
    key: str = "", *, enabled: bool = True, **kwargs: Unpack[_BinarySensorKwargs]
) -> EcoflowBinarySensorEntityDescription:
    return _make_desc(BinarySensorDeviceClass.PROBLEM, key, enabled=enabled, **kwargs)


def safety(
    key: str = "", *, enabled: bool = True, **kwargs: Unpack[_BinarySensorKwargs]
) -> EcoflowBinarySensorEntityDescription:
    return _make_desc(BinarySensorDeviceClass.SAFETY, key, enabled=enabled, **kwargs)


def plug(
    key: str = "", *, enabled: bool = True, **kwargs: Unpack[_BinarySensorKwargs]
) -> EcoflowBinarySensorEntityDescription:
    return _make_desc(BinarySensorDeviceClass.PLUG, key, enabled=enabled, **kwargs)


def battery(
    key: str = "", *, enabled: bool = True, **kwargs: Unpack[_BinarySensorKwargs]
) -> EcoflowBinarySensorEntityDescription:
    return _make_desc(BinarySensorDeviceClass.BATTERY, key, enabled=enabled, **kwargs)


def power(
    key: str = "", *, enabled: bool = True, **kwargs: Unpack[_BinarySensorKwargs]
) -> EcoflowBinarySensorEntityDescription:
    return _make_desc(BinarySensorDeviceClass.POWER, key, enabled=enabled, **kwargs)


def connectivity(
    key: str = "", *, enabled: bool = True, **kwargs: Unpack[_BinarySensorKwargs]
) -> EcoflowBinarySensorEntityDescription:
    return _make_desc(
        BinarySensorDeviceClass.CONNECTIVITY, key, enabled=enabled, **kwargs
    )


def battery_charging(
    key: str = "", *, enabled: bool = True, **kwargs: Unpack[_BinarySensorKwargs]
) -> EcoflowBinarySensorEntityDescription:
    return _make_desc(
        BinarySensorDeviceClass.BATTERY_CHARGING, key, enabled=enabled, **kwargs
    )


_shp2_channel_range = range(1, shp2.Device.NUM_OF_CHANNELS + 1)


def shp2_channel(
    fn: Callable[..., EcoflowBinarySensorEntityDescription],
    translation_key: str,
    **kwargs,
) -> EcoflowBinarySensorEntityDescription:
    """Indexed SHP2 channel binary sensor with channel placeholder pre-filled."""
    return fn(
        translation_key=translation_key,
        translation_placeholders={"channel": "{n}"},
        indexed_range=_shp2_channel_range,
        **kwargs,
    )


_BINARY_SENSORS: Final[dict[str, BinarySensorEntityDescription]] = {
    "error_happened": problem("error", entity_category=EntityCategory.DIAGNOSTIC),
    "plugged_in_ac": plug(),
    "error_occurred": problem(
        enabled=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_attribute_fields=["error_code"],
    ),
    "bms_run_state": power(enabled=False, entity_category=EntityCategory.DIAGNOSTIC),
    # SHP2 backup channel binary sensors
    "ch{n}_backup_is_ready": shp2_channel(
        battery, "channel_backup_is_ready", enabled=False
    ),
    "ch{n}_force_charge": shp2_channel(power, "backup_force_charge", enabled=False),
    # SHP2 energy binary sensors
    "channel{n}_is_enabled": shp2_channel(power, "channel_is_enabled", enabled=False),
    "channel{n}_is_connected": shp2_channel(connectivity, "channel_is_connected"),
    "channel{n}_is_ac_open": shp2_channel(power, "channel_is_ac_open", enabled=False),
    "channel{n}_is_power_output": shp2_channel(
        power, "channel_is_power_output", enabled=False
    ),
    "channel{n}_is_grid_charge": shp2_channel(
        battery_charging, "channel_is_grid_charge", enabled=False
    ),
    "channel{n}_is_mppt_charge": shp2_channel(
        battery_charging, "channel_is_mppt_charge", enabled=False
    ),
    "channel{n}_ems_charging": shp2_channel(
        power, "channel_ems_charging", enabled=False
    ),
    "channel{n}_hw_connected": shp2_channel(
        connectivity, "channel_hw_connected", enabled=False
    ),
    # SHP2 generic binary sensors
    "grid_status": connectivity(enabled=True),
    "storm_mode": safety(enabled=True),
    # DPU
    "is_charging": battery_charging(
        enabled=False, entity_category=EntityCategory.DIAGNOSTIC
    ),
    "slow_charging": power(enabled=False, entity_category=EntityCategory.DIAGNOSTIC),
    "ac_allowed": lock(enabled=False, entity_category=EntityCategory.DIAGNOSTIC),
    "hv_solar_weak": problem(enabled=False, entity_category=EntityCategory.DIAGNOSTIC),
    "lv_solar_weak": problem(enabled=False, entity_category=EntityCategory.DIAGNOSTIC),
    "hv_solar_low_voltage": problem(
        enabled=False, entity_category=EntityCategory.DIAGNOSTIC
    ),
    "lv_solar_low_voltage": problem(
        enabled=False, entity_category=EntityCategory.DIAGNOSTIC
    ),
}

BINARY_SENSOR_TYPES: Final[dict[str, BinarySensorEntityDescription]] = (
    resolve_entity_description_keys(_BINARY_SENSORS)
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add binary sensors for passed config_entry in HA."""
    device = config_entry.runtime_data

    new_sensors = [
        EcoflowBinarySensor(device, sensor)
        for sensor in BINARY_SENSOR_TYPES
        if hasattr(device, sensor)
    ]

    if new_sensors:
        async_add_entities(new_sensors)


class EcoflowBinarySensor(EcoflowEntity, BinarySensorEntity):
    def __init__(
        self,
        device: DeviceBase,
        sensor: str,
    ):
        super().__init__(device)

        self._attr_unique_id = f"ef_{self._device.serial_number}_{sensor}"
        self._attr_is_on = getattr(self._device, sensor, None)

        if sensor in BINARY_SENSOR_TYPES:
            self.entity_description = BINARY_SENSOR_TYPES[sensor]
            self._prop_name = self.entity_description.key
            if self.entity_description.translation_key is None:
                self._attr_translation_key = self.entity_description.key

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""
        self._device.register_state_update_callback(self.state_updated, self._prop_name)
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        self._device.remove_state_update_callback(self.state_updated, self._prop_name)
        await super().async_will_remove_from_hass()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes from configured attribute fields."""
        if not isinstance(
            self.entity_description, EcoflowBinarySensorEntityDescription
        ):
            return None

        return {
            field_name: getattr(self._device, field_name)
            for field_name in self.entity_description.state_attribute_fields
            if hasattr(self._device, field_name)
        } or None

    @callback
    def state_updated(self, state: bool):
        self._attr_is_on = state
        self.async_write_ha_state()

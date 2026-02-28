"""EcoFlow BLE binary sensor"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

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
from .entity import EcoflowEntity

_LOGGER = logging.getLogger(__name__)


def _create_shp2_binary_sensors():
    """Create binary sensor descriptions for SHP2 backup channel and energy info"""
    sensors = {}

    # Backup channel binary sensors
    for i in range(1, shp2.Device.NUM_OF_CHANNELS + 1):
        sensors[f"ch{i}_backup_is_ready"] = BinarySensorEntityDescription(
            key=f"ch{i}_backup_is_ready",
            translation_key="channel_backup_is_ready",
            translation_placeholders={"channel": f"{i}"},
            device_class=BinarySensorDeviceClass.BATTERY,
            entity_registry_enabled_default=False,
        )

    # Energy binary sensors
    for i in range(1, shp2.Device.NUM_OF_CHANNELS + 1):
        sensors.update(
            {
                f"channel{i}_is_enabled": BinarySensorEntityDescription(
                    key=f"channel{i}_is_enabled",
                    translation_key="channel_is_enabled",
                    translation_placeholders={"channel": f"{i}"},
                    device_class=BinarySensorDeviceClass.POWER,
                ),
                f"channel{i}_is_connected": BinarySensorEntityDescription(
                    key=f"channel{i}_is_connected",
                    translation_key="channel_is_connected",
                    translation_placeholders={"channel": f"{i}"},
                    device_class=BinarySensorDeviceClass.CONNECTIVITY,
                ),
                f"channel{i}_is_ac_open": BinarySensorEntityDescription(
                    key=f"channel{i}_is_ac_open",
                    translation_key="channel_is_ac_open",
                    translation_placeholders={"channel": f"{i}"},
                    device_class=BinarySensorDeviceClass.POWER,
                    entity_registry_enabled_default=False,
                ),
                f"channel{i}_is_power_output": BinarySensorEntityDescription(
                    key=f"channel{i}_is_power_output",
                    translation_key="channel_is_power_output",
                    translation_placeholders={"channel": f"{i}"},
                    device_class=BinarySensorDeviceClass.POWER,
                    entity_registry_enabled_default=False,
                ),
                f"channel{i}_is_grid_charge": BinarySensorEntityDescription(
                    key=f"channel{i}_is_grid_charge",
                    translation_key="channel_is_grid_charge",
                    translation_placeholders={"channel": f"{i}"},
                    device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
                    entity_registry_enabled_default=False,
                ),
                f"channel{i}_is_mppt_charge": BinarySensorEntityDescription(
                    key=f"channel{i}_is_mppt_charge",
                    translation_key="channel_is_mppt_charge",
                    translation_placeholders={"channel": f"{i}"},
                    device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
                    entity_registry_enabled_default=False,
                ),
                f"channel{i}_ems_charging": BinarySensorEntityDescription(
                    key=f"channel{i}_ems_charging",
                    translation_key="channel_ems_charging",
                    translation_placeholders={"channel": f"{i}"},
                    device_class=BinarySensorDeviceClass.POWER,
                    entity_registry_enabled_default=False,
                ),
                f"channel{i}_hw_connected": BinarySensorEntityDescription(
                    key=f"channel{i}_hw_connected",
                    translation_key="channel_hw_connected",
                    translation_placeholders={"channel": f"{i}"},
                    device_class=BinarySensorDeviceClass.CONNECTIVITY,
                    entity_registry_enabled_default=False,
                ),
            }
        )

    return sensors


@dataclass(frozen=True, kw_only=True)
class EcoflowBinarySensorEntityDescription(BinarySensorEntityDescription):
    update_state: Callable[[bool], None] | None = None


BINARY_SENSOR_TYPES = {
    "error_happened": BinarySensorEntityDescription(
        key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "plugged_in_ac": BinarySensorEntityDescription(
        key="plugged_in_ac",
        device_class=BinarySensorDeviceClass.PLUG,
    ),
    # SHP2 Binary Sensors - dynamically generated
    **_create_shp2_binary_sensors(),
}


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
        if sensor in BINARY_SENSOR_TYPES:
            self.entity_description = BINARY_SENSOR_TYPES[sensor]
            self._prop_name = self.entity_description.key
            if self.entity_description.translation_key is None:
                self._attr_translation_key = self.entity_description.key

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""
        self._device.register_state_update_callback(self.state_updated, self._prop_name)

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        self._device.remove_state_update_calback(self.state_updated, self._prop_name)

    @callback
    def state_updated(self, state: bool):
        self._attr_is_on = state
        self.async_write_ha_state()

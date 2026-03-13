import dataclasses
from collections.abc import Callable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER
from .eflib import DeviceBase
from .eflib.device_mappings import battery_name_from_device


def resolve_entity_description_keys(
    descriptions: dict[str, Any],
    indexed_type: type,
) -> dict[str, Any]:
    """
    Fill in description keys from dict key, and expand indexed ({n}) descriptions.

    Descriptions with {n} in their key that are instances of indexed_type with
    indexed_range set are expanded across the range. {n} in translation_placeholder
    values is also replaced, supporting format specs like {n:02d}.
    """
    result = {}
    for k, v in descriptions.items():
        if "{n}" in k and isinstance(v, indexed_type) and v.indexed_range is not None:
            for i in v.indexed_range:
                actual_key = k.replace("{n}", str(i))
                placeholders = v.translation_placeholders
                if placeholders:
                    placeholders = {
                        pk: pv.format(n=i) for pk, pv in placeholders.items()
                    }
                result[actual_key] = dataclasses.replace(
                    v,
                    key=actual_key,
                    indexed_range=None,
                    translation_placeholders=placeholders,
                )
            continue

        result[k] = dataclasses.replace(v, key=k) if not v.key else v
    return result


class EcoflowEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, device: DeviceBase):
        self._device = device
        self._update_callbacks: list[tuple[str, Callable[[Any], None]]] = []

    @property
    def device_info(self):
        """Return information to link this entity with the correct device."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self._device.address),
            },
            connections={
                (CONNECTION_BLUETOOTH, self._device.address),
            },
            name=self._device.name,
            manufacturer=MANUFACTURER,
            model=self._device.device,
            serial_number=self._device.serial_number,
        )

    @property
    def available(self) -> bool:
        """Return True if device is connected."""
        return self._device.is_connected

    class SkipWrite:
        """Sentinel value for skipping write in update callback"""

    def _register_update_callback(
        self,
        entity_attr: str,
        prop_name: str | None,
        get_state: Callable[[Any], SkipWrite | Any] = lambda x: x,
        default_state: Any = None,
    ):
        if prop_name is None:
            return

        @callback
        def state_updated(state: Any):
            if (state := get_state(state)) is EcoflowEntity.SkipWrite:
                return

            setattr(self, entity_attr, state)
            self.async_write_ha_state()

        if (state := getattr(self._device, prop_name, None)) is not None:
            setattr(self, entity_attr, get_state(state))
        elif default_state is not None:
            setattr(self, entity_attr, default_state)

        self._update_callbacks.append((prop_name, state_updated))

    async def async_added_to_hass(self) -> None:
        for prop, state_callback in self._update_callbacks:
            self._device.register_state_update_callback(state_callback, prop)
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self) -> None:
        for prop, state_callback in self._update_callbacks:
            self._device.remove_state_update_calback(state_callback, prop)
        await super().async_will_remove_from_hass()


class EcoflowBatteryAddonEntity(EcoflowEntity):
    def __init__(
        self,
        device: DeviceBase,
        battery_index: int,
    ) -> None:
        super().__init__(device)
        self._battery_index = battery_index

    @property
    def device_info(self) -> DeviceInfo:
        battery_sn = getattr(self._device, f"battery_{self._battery_index}_sn", None)
        battery_model = battery_name_from_device(self._device, self._battery_index)

        return DeviceInfo(
            identifiers={
                (DOMAIN, f"{self._device.address}_battery_{self._battery_index}"),
            },
            name=f"{self._device.name} Extra Battery {self._battery_index}",
            manufacturer=MANUFACTURER,
            model=battery_model,
            serial_number=battery_sn,
            via_device=(DOMAIN, self._device.address),
        )

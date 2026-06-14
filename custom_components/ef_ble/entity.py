import dataclasses
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from .const import DOMAIN, MANUFACTURER
from .eflib import DeviceBase
from .eflib.device_mappings import battery_name_from_device


class EcoflowEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, device: DeviceBase):
        self._device = device
        self._update_callbacks: list[tuple[str, Callable[[Any], None]]] = []

    @property
    def device_info(self):
        """Return information to link this entity with the correct device"""
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
        """Return True if device is connected"""
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
        if prop_name is None or not hasattr(self._device, prop_name):
            return

        @callback
        def state_updated(state: Any):
            if (state := get_state(state)) is EcoflowEntity.SkipWrite:
                return

            setattr(self, entity_attr, state)
            self.async_write_ha_state()

        device_state = getattr(self._device, prop_name, None)
        if device_state is None and default_state is not None:
            setattr(self, entity_attr, default_state)
        elif (initial := get_state(device_state)) is not EcoflowEntity.SkipWrite:
            setattr(self, entity_attr, initial)

        self._update_callbacks.append((prop_name, state_updated))

    async def async_added_to_hass(self) -> None:
        for prop, state_callback in self._update_callbacks:
            self._device.register_state_update_callback(state_callback, prop)
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self) -> None:
        for prop, state_callback in self._update_callbacks:
            self._device.remove_state_update_callback(state_callback, prop)
        await super().async_will_remove_from_hass()


class EcoflowBatteryAddonEntity(EcoflowEntity):
    def __init__(
        self,
        device: DeviceBase,
        battery_index: int,
    ) -> None:
        super().__init__(device)
        self._battery_index = battery_index
        self._sn_prop = f"battery_{battery_index}_sn"

    @property
    def device_info(self) -> DeviceInfo:
        battery_sn = getattr(self._device, self._sn_prop, None)
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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._device.register_state_update_callback(
            self._refresh_device_registry, self._sn_prop
        )

    async def async_will_remove_from_hass(self) -> None:
        self._device.remove_state_update_callback(
            self._refresh_device_registry, self._sn_prop
        )
        await super().async_will_remove_from_hass()

    @callback
    def _refresh_device_registry(self, battery_sn: str | None) -> None:
        """Push a late-arriving battery serial number into the device registry"""
        if not battery_sn:
            return

        registry = dr.async_get(self.hass)
        identifier = (DOMAIN, f"{self._device.address}_battery_{self._battery_index}")
        device_entry = registry.async_get_device(identifiers={identifier})
        if device_entry is None:
            return

        battery_model = battery_name_from_device(self._device, self._battery_index)
        if (
            device_entry.serial_number == battery_sn
            and device_entry.model == battery_model
        ):
            return

        registry.async_update_device(
            device_entry.id, serial_number=battery_sn, model=battery_model
        )


@runtime_checkable
class IndexableDescription(Protocol):
    """Entity description that supports indexed expansion via `{n}` in keys"""

    key: str
    indexed_range: range | None
    translation_placeholders: Mapping[str, str] | None


def resolve_entity_description_keys[D: EntityDescription](
    descriptions: dict[str, D],
) -> dict[str, D]:
    """
    Fill in description keys from dict key, and expand indexed ({n}) descriptions.

    Descriptions with {n} in their key that are instances of indexed_type with
    indexed_range set are expanded across the range. {n} in translation_placeholder
    values is also replaced, supporting format specs like {n:02d}.
    """
    result: dict[str, D] = {}
    for k, v in descriptions.items():
        if not (
            "{n}" in k
            and isinstance(v, IndexableDescription)
            and v.indexed_range is not None
        ):
            result[k] = dataclasses.replace(v, key=k) if not v.key else v
            continue

        for i in v.indexed_range:
            actual_key = k.replace("{n}", str(i))
            placeholders = v.translation_placeholders
            if placeholders:
                placeholders = {pk: pv.format(n=i) for pk, pv in placeholders.items()}
            result[actual_key] = dataclasses.replace(
                v,
                key=actual_key,
                indexed_range=None,
                translation_placeholders=placeholders,
            )

    return result

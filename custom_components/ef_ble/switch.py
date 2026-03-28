import dataclasses
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceConfigEntry
from .deprecated.switches import DEPRECATED_SWITCH_TYPES
from .description_builder import EntityDescriptionBuilder
from .eflib import DeviceBase, get_controls
from .eflib.entity import controls
from .entity import EcoflowEntity


@dataclass(frozen=True, kw_only=True)
class EcoflowSwitchEntityDescription[T: DeviceBase](SwitchEntityDescription):
    set_state: Callable[[T, bool], Awaitable] | None = None
    availability_prop: str | None = None


@dataclass(init=False)
class SwitchBuilder(EntityDescriptionBuilder):
    _device_class: SwitchDeviceClass | None = None
    _enable_func: Callable[[DeviceBase, bool], Awaitable[None]] | None = None

    def device_class(self, device_class: SwitchDeviceClass):
        self._device_class = device_class
        return self

    def enable_func(self, func: Callable[[DeviceBase, bool], Awaitable[None]]):
        self._enable_func = func
        return self

    def build(self):
        if self._enable_func is None:
            raise ValueError("Cannot build switch entity without enable func")
        return EcoflowSwitchEntityDescription(
            key=self._entity_key,
            name=self._entity_name,
            device_class=self._device_class,
            entity_category=self._entity_category,
            set_state=self._enable_func,
            entity_registry_enabled_default=self._entity_registry_enabled_default,
            translation_key=self._entity_translation_key,
            translation_placeholders=self._translation_placeholders,
            availability_prop=self._availability_prop,
            icon=self._icon,
        )


@dataclasses.dataclass
class _Builder[E: controls.ControlType]:
    builder: Callable[[E, SwitchBuilder], SwitchBuilder]


_BUILDERS: dict[type[controls.ControlType], _Builder] = {
    controls.outlet: _Builder[controls.outlet](
        lambda outlet, builder: builder.device_class(SwitchDeviceClass.OUTLET)
    ),
    controls.switch: _Builder[controls.switch](
        lambda switch, builder: builder.device_class(SwitchDeviceClass.SWITCH)
    ),
    controls.toggle: _Builder[controls.toggle](lambda toggle, builder: builder),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    device = entry.runtime_data

    # New controls system (devices migrated to @controls decorators)
    descriptions = [
        (
            _BUILDERS[switch.__class__]
            .builder(switch, SwitchBuilder.from_entity(switch))
            .enable_func(switch.enable_func)
            .build()
        )
        for switch in get_controls(device, controls.toggle)
    ]

    if not descriptions:
        # Deprecated: old hardcoded list (for devices not yet migrated)
        descriptions = [
            desc
            for desc in DEPRECATED_SWITCH_TYPES
            if (
                hasattr(device, desc.key)
                and (
                    isinstance(desc, EcoflowSwitchEntityDescription)
                    or hasattr(device, f"enable_{desc.key}")
                )
            )
        ]

    entities = [EcoflowSwitchEntity(device, desc) for desc in descriptions]
    if entities:
        async_add_entities(entities)


class EcoflowSwitchEntity(EcoflowEntity, SwitchEntity):
    def __init__(
        self, device: DeviceBase, entity_description: SwitchEntityDescription
    ) -> None:
        super().__init__(device)

        self._attr_unique_id = f"ef_{device.serial_number}_{entity_description.key}"
        self._prop_name = entity_description.key
        self._set_state = getattr(device, f"enable_{self._prop_name}", None)
        self.entity_description = entity_description
        self._on_off_state = getattr(device, self._prop_name, None)
        self._availability_prop = getattr(entity_description, "availability_prop", None)

        if entity_description.translation_key is None:
            self._attr_translation_key = self.entity_description.key

        self._register_update_callback(
            entity_attr="_attr_available",
            prop_name=self._availability_prop,
            get_state=lambda state: state if state is not None else self.SkipWrite,
        )

        custom_set_state = getattr(entity_description, "set_state", None)
        if isinstance(custom_set_state, Callable):
            self._set_state = partial(custom_set_state, device)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if isinstance(self._set_state, Callable):
            await self._set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if isinstance(self._set_state, Callable):
            await self._set_state(False)

    async def async_added_to_hass(self) -> None:
        self._device.register_state_update_callback(self.state_updated, self._prop_name)
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._device.remove_state_update_callback(self.state_updated, self._prop_name)
        await super().async_will_remove_from_hass()

    @callback
    def state_updated(self, state: bool | None):
        self._on_off_state = state
        self.async_write_ha_state()

    @callback
    def availability_updated(self, state: bool):
        self._attr_available = state
        self.async_write_ha_state()

    @property
    def available(self):
        if not super().available or self._on_off_state is None:
            return False
        if self._availability_prop is not None:
            return self._attr_available
        return True

    @property
    def is_on(self):
        return self._on_off_state if self._on_off_state is not None else False

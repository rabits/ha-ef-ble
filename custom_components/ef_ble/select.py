import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any, Self

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceConfigEntry
from .deprecated.selects import SELECT_TYPES
from .description_builder import EntityDescriptionBuilder
from .eflib import DeviceBase, controls, get_controls
from .eflib.entity import DynamicValue
from .entity import EcoflowEntity


@dataclasses.dataclass(kw_only=True, frozen=True)
class EcoflowSelectEntityDescription[T: DeviceBase](SelectEntityDescription):
    set_state: Callable[[T, str], Awaitable] | None = None
    availability_prop: str | None = None
    conditional_options: tuple[tuple[DynamicValue, list[str]], ...] = ()


class SelectSensorBuilder(EntityDescriptionBuilder):
    def __init__(self):
        self._options = None
        self._async_set_native_value = None
        self._availability_prop = None
        self._conditional_options = ()

    def options(self, options: list[str]):
        self._options = options
        return self

    def conditional_options(
        self, conditional: list[tuple[DynamicValue, list[str]]]
    ) -> Self:
        self._conditional_options = tuple(conditional)
        return self

    def async_set_native_value(
        self, func: Callable[[DeviceBase, Any], Awaitable[None]]
    ):
        self._async_set_native_value = func
        return self

    def set_state(self, func: Callable[[DeviceBase, Any], Awaitable[None]]):
        self._async_set_native_value = func
        return self

    def build(self):
        if self._field is None:
            raise ValueError("Cannot build select entity without field")
        return EcoflowSelectEntityDescription(
            key=self._entity_key,
            name=self._entity_name,
            options=self._options,
            set_state=self._async_set_native_value,
            translation_key=self._entity_translation_key,
            entity_registry_enabled_default=self._entity_registry_enabled_default,
            availability_prop=self._availability_prop,
            conditional_options=self._conditional_options,
            icon=self._icon,
        )


@dataclasses.dataclass
class _Builder[E: controls.select]:
    builder: Callable[[E, SelectSensorBuilder], SelectSensorBuilder]


_BUILDERS = {
    controls.select: _Builder[controls.select](lambda select, builder: builder),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add select entities for passed config_entry in HA."""
    device = config_entry.runtime_data

    # New controls system (devices migrated to @controls decorators)
    descriptions = [
        (
            _BUILDERS[select.__class__]
            .builder(select, SelectSensorBuilder.from_entity(select))
            .set_state(select.set_value_func)
            .availability_prop(select.availability_prop)
            .conditional_options(select.conditional_options)
            .options(select.options_str)
            .build()
        )
        for select in get_controls(device, control_type=controls.select)
    ]

    if not descriptions:
        # Deprecated: old hardcoded list (for devices not yet migrated)
        descriptions = [desc for desc in SELECT_TYPES if hasattr(device, desc.key)]

    entities = [EcoflowSelect(device, desc) for desc in descriptions]
    if entities:
        async_add_entities(entities)


class EcoflowSelect(EcoflowEntity, SelectEntity):
    def __init__(
        self,
        device: DeviceBase,
        description: EcoflowSelectEntityDescription[DeviceBase],
    ):
        super().__init__(device)

        self._attr_unique_id = f"ef_{self._device.serial_number}_{description.key}"
        self.entity_description = description
        self._prop_name = self.entity_description.key
        self._set_state = description.set_state
        self._attr_current_option = getattr(device, self._prop_name, None)
        self._availability_prop = description.availability_prop
        self._offered_options = list(description.options or [])
        # The deprecated descriptions this platform falls back to are a separate class
        # that carries no conditions
        self._conditional_options: tuple[tuple[DynamicValue, list[str]], ...] = getattr(
            description, "conditional_options", ()
        )
        self._attr_options = self._options_now()

        if self.entity_description.translation_key is None:
            self._attr_translation_key = self.entity_description.key

        self._register_update_callback(
            entity_attr="_attr_current_option",
            prop_name=self._prop_name,
            get_state=(
                lambda value: (
                    value.name.lower() if value is not None else self.SkipWrite
                )
            ),
        )
        self._register_update_callback(
            entity_attr="_attr_available",
            prop_name=self._availability_prop,
            get_state=lambda state: state if state is not None else self.SkipWrite,
        )
        for condition, _ in self._conditional_options:
            self._register_update_callback(
                entity_attr="_attr_options",
                prop_name=condition.prop_name,
                get_state=lambda _: self._options_now(),
            )

    def _options_now(self) -> list[str]:
        withheld = {
            option
            for condition, options in self._conditional_options
            if condition.resolve(self._device)
            for option in options
        }
        withheld.discard(self._attr_current_option)
        return [option for option in self._offered_options if option not in withheld]

    @property
    def available(self):
        is_available = super().available
        if not is_available or self._availability_prop is None:
            return is_available

        return self._attr_available

    @callback
    def availability_updated(self, state: bool):
        self._attr_available = state
        self.async_write_ha_state()
        self._register_update_callback(
            entity_attr="_attr_current_option",
            prop_name=self._prop_name,
            get_state=(
                lambda value: (
                    value.name.lower() if value is not None else self.SkipWrite
                )
            ),
        )

    async def async_select_option(self, option: str) -> None:
        if self._set_state is not None:
            await self._set_state(self._device, option)
            return

        await super().async_select_option(option)

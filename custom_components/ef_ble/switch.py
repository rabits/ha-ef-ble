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
from .description_builder import EntityDescriptionBuilder
from .eflib import DeviceBase, get_controls
from .eflib.devices import dpu, shp2
from .eflib.entity import controls
from .entity import EcoflowEntity


@dataclass(frozen=True, kw_only=True)
class EcoflowSwitchEntityDescription[T: DeviceBase](SwitchEntityDescription):
    set_state: Callable[[T, bool], Awaitable] | None = None
    availability_prop: str | None = None


SWITCH_TYPES = [
    SwitchEntityDescription(
        key="dc_12v_port",
        name="DC 12V Port",
        device_class=SwitchDeviceClass.OUTLET,
    ),
    SwitchEntityDescription(
        key="dc_ports",
        device_class=SwitchDeviceClass.OUTLET,
    ),
    EcoflowSwitchEntityDescription[dpu.Device](
        key="ac_ports",
        device_class=SwitchDeviceClass.OUTLET,
        availability_prop="ac_ports_availability",
    ),
    SwitchEntityDescription(
        key="ac_ports_2",
        name="AC Ports (2)",
        device_class=SwitchDeviceClass.OUTLET,
    ),
    SwitchEntityDescription(
        key="ac_port",
        name="AC Port",
        device_class=SwitchDeviceClass.OUTLET,
    ),
    SwitchEntityDescription(
        key="disable_grid_bypass",
        name="Disable Grid Bypass",
        entity_registry_enabled_default=False,
    ),
    SwitchEntityDescription(
        key="self_start",
        name="Self Start",
    ),
    SwitchEntityDescription(
        key="ac_lv_port",
        name="LV AC",
        device_class=SwitchDeviceClass.OUTLET,
    ),
    SwitchEntityDescription(
        key="ac_hv_port",
        name="HV AC",
        device_class=SwitchDeviceClass.OUTLET,
    ),
    SwitchEntityDescription(
        key="energy_backup",
        name="Backup Reserve",
        device_class=SwitchDeviceClass.SWITCH,
        translation_key="battery_sync",
    ),
    SwitchEntityDescription(
        key="usb_ports",
        name="USB Ports",
        icon="mdi:usb",
    ),
    SwitchEntityDescription(
        key="engine_on",
        name="Engine",
    ),
    SwitchEntityDescription(
        key="charger_open",
        name="Charger",
    ),
    SwitchEntityDescription(
        key="lpg_level_monitoring",
        name="LPG Level Monitoring",
    ),
    SwitchEntityDescription(
        key="ac_1",
        name="AC (1)",
        device_class=SwitchDeviceClass.OUTLET,
    ),
    SwitchEntityDescription(
        key="ac_2",
        name="AC (2)",
        device_class=SwitchDeviceClass.OUTLET,
    ),
    SwitchEntityDescription(
        key="feed_grid",
        name="Feed Grid",
    ),
    SwitchEntityDescription(
        key="power",
        name="Power",
        device_class=SwitchDeviceClass.SWITCH,
    ),
    SwitchEntityDescription(
        key="energy_strategy_self_powered",
        name="Self-Powered Mode",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:solar-power",
    ),
    SwitchEntityDescription(
        key="energy_strategy_scheduled",
        name="Scheduled Mode",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:calendar-clock",
    ),
    SwitchEntityDescription(
        key="energy_strategy_tou",
        name="Time-of-Use Mode",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:clock-time-eight",
    ),
    SwitchEntityDescription(
        key="automatic_drain",
        name="Automatic Drain",
    ),
    SwitchEntityDescription(
        key="ambient_light",
        name="Ambient Light",
    ),
    SwitchEntityDescription(
        key="emergency_reverse_charging",
        name="Emergency Reverse Charging",
    ),
    EcoflowSwitchEntityDescription[shp2.Device](
        key="eps_mode",
        device_class=SwitchDeviceClass.SWITCH,
        set_state=lambda device, value: device.set_eps_mode(value),
    ),
    # SHP2 Circuit switches
    *[
        EcoflowSwitchEntityDescription[shp2.Device](
            key=f"circuit_{i}",
            translation_key="circuit_is_enabled",
            translation_placeholders={"circuit": f"{i}"},
            device_class=SwitchDeviceClass.OUTLET,
            set_state=lambda device, value, i=i: device.set_circuit_power(i, value),
            availability_prop=f"circuit_{i}_split_info_loaded",
        )
        for i in range(1, shp2.Device.NUM_OF_CIRCUITS + 1)
    ],
    # SHP2 Channels switches
    *[
        EcoflowSwitchEntityDescription[shp2.Device](
            key=f"channel{i}_is_enabled",
            translation_key="channel_is_enabled",
            translation_placeholders={"channel": f"{i}"},
            device_class=SwitchDeviceClass.SWITCH,
            set_state=lambda device, enabled, i=i: device.set_channel_enable(
                i, enabled
            ),
            availability_prop=f"channel{i}_is_connected",
        )
        for i in range(1, shp2.Device.NUM_OF_CHANNELS + 1)
    ],
    *[
        EcoflowSwitchEntityDescription[shp2.Device](
            key=f"ch{i}_force_charge",
            translation_key="ch_force_charge",
            translation_placeholders={"channel": f"{i}"},
            device_class=SwitchDeviceClass.SWITCH,
            set_state=lambda device, enabled, i=i: device.set_channel_force_charge(
                i, enabled
            ),
            availability_prop=f"channel{i}_is_connected",
        )
        for i in range(1, shp2.Device.NUM_OF_CHANNELS + 1)
    ],
]


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


def _build_control_switches(device: DeviceBase) -> list[SwitchEntityDescription]:
    return [
        (
            _BUILDERS[switch.__class__]
            .builder(switch, SwitchBuilder.from_entity(switch))
            .enable_func(switch.enable_func)
            .build()
        )
        for switch in get_controls(device, controls.toggle)
        if switch.__class__ in _BUILDERS and switch.enable_func is not None
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    device = entry.runtime_data

    # New controls system (devices migrated to @controls decorators)
    control_descs = _build_control_switches(device)
    control_keys = {d.key for d in control_descs}

    # Deprecated: old hardcoded list (for devices not yet migrated)
    legacy_descs = [
        desc
        for desc in SWITCH_TYPES
        if (
            desc.key not in control_keys
            and hasattr(device, desc.key)
            and (
                isinstance(desc, EcoflowSwitchEntityDescription)
                or hasattr(device, f"enable_{desc.key}")
            )
        )
    ]

    entities = [
        EcoflowSwitchEntity(device, desc) for desc in [*control_descs, *legacy_descs]
    ]
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

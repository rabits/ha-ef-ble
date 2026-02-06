from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceConfigEntry
from .eflib import DeviceBase
from .eflib.devices import (
    alternator_charger,
    river2,
    river3,
    river3_plus,
    smart_generator,
    stream_ac,
    wave2,
)
from .entity import EcoflowEntity


@dataclass(kw_only=True, frozen=True)
class EcoflowSelectEntityDescription[T: DeviceBase](SelectEntityDescription):
    set_state: Callable[[T, str], Awaitable] | None = None

    availability_prop: str | None = None


SELECT_TYPES: list[EcoflowSelectEntityDescription] = [
    # River 3 Plus
    EcoflowSelectEntityDescription[river3_plus.Device](
        key="led_mode",
        options=river3_plus.LedMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_led_mode(
                river3_plus.LedMode[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[river3.Device](
        key="dc_charging_type",
        name="DC Charging Type",
        options=river3.DcChargingType.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_dc_charging_type(
                river3.DcChargingType[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[river2.Device](
        key="dc_mode",
        name="DC Mode",
        options=river2.DCMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_dc_mode(river2.DCMode[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[smart_generator.Device](
        key="performance_mode",
        options=smart_generator.PerformanceMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_performance_mode(
                smart_generator.PerformanceMode[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[smart_generator.Device](
        key="liquefied_gas_unit",
        options=smart_generator.LiquefiedGasUnit.options(include_unknown=False),
        availability_prop="lpg_level_monitoring",
        set_state=(
            lambda device, value: device.set_liquefied_gas_unit(
                smart_generator.LiquefiedGasUnit[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[alternator_charger.Device](
        key="charger_mode",
        options=alternator_charger.ChargerMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_charger_mode(
                alternator_charger.ChargerMode[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[stream_ac.Device](
        key="energy_strategy",
        name="Energy Strategy",
        options=stream_ac.EnergyStrategy.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_energy_strategy(
                stream_ac.EnergyStrategy[value.upper()]
            )
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="power_mode",
        name="Power Mode",
        options=wave2.PowerMode.options(
            include_unknown=False, exclude=[wave2.PowerMode.INIT]
        ),
        set_state=(
            lambda device, value: device.set_power_mode(wave2.PowerMode[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="main_mode",
        name="Main Mode",
        options=wave2.MainMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_main_mode(wave2.MainMode[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="sub_mode",
        name="Sub Mode",
        options=wave2.SubMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_sub_mode(wave2.SubMode[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="fan_speed",
        name="Fan Speed",
        options=wave2.FanGear.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_fan_speed(wave2.FanGear[value.upper()])
        ),
    ),
    EcoflowSelectEntityDescription[wave2.Device](
        key="drain_mode",
        name="Drain Mode",
        options=wave2.DrainMode.options(include_unknown=False),
        set_state=(
            lambda device, value: device.set_drain_mode(wave2.DrainMode[value.upper()])
        ),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeviceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add binary sensors for passed config_entry in HA."""
    device = config_entry.runtime_data

    new_sensors = [
        EcoflowSelect(device, description)
        for description in SELECT_TYPES
        if hasattr(device, description.key)
    ]

    if new_sensors:
        async_add_entities(new_sensors)


class EcoflowSelect(EcoflowEntity, SelectEntity):
    def __init__(
        self,
        device: DeviceBase,
        description: EcoflowSelectEntityDescription[DeviceBase],
    ):
        super().__init__(device)

        self._attr_unique_id = f"{self._device.name}_{description.key}"
        self.entity_description = description
        self._prop_name = self.entity_description.key
        self._set_state = description.set_state
        self._attr_current_option = None
        self._availability_prop = description.availability_prop

        if self.entity_description.translation_key is None:
            self._attr_translation_key = self.entity_description.key

        self._register_update_callback(
            entity_attr="_attr_current_option",
            prop_name=self._prop_name,
            get_state=(
                lambda value: value.name.lower()
                if value is not None
                else self.SkipWrite
            ),
        )
        self._register_update_callback(
            entity_attr="_attr_available",
            prop_name=self._availability_prop,
            get_state=lambda state: state if state is not None else self.SkipWrite,
        )

    @property
    def available(self):
        is_available = super().available
        if not is_available or self._availability_prop is None:
            return is_available

        return self._attr_available

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""
        await super().async_added_to_hass()

        if self._availability_prop is not None:
            self._device.register_state_update_callback(
                self.availability_updated,
                self._availability_prop,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        await super().async_will_remove_from_hass()
        if self._availability_prop is not None:
            self._device.remove_state_update_calback(
                self.availability_updated,
                self._availability_prop,
            )

    @callback
    def availability_updated(self, state: bool):
        self._attr_available = state
        self.async_write_ha_state()
        self._register_update_callback(
            entity_attr="_attr_current_option",
            prop_name=self._prop_name,
            get_state=(
                lambda value: value.name.lower()
                if value is not None
                else self.SkipWrite
            ),
        )

    async def async_select_option(self, option: str) -> None:
        if self._set_state is not None:
            await self._set_state(self._device, option)
            return

        await super().async_select_option(option)

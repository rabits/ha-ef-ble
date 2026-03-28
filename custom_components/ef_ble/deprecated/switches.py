"""Deprecated: hardcoded switch entity descriptions for unmigrated devices"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntityDescription

from ..eflib import DeviceBase
from ..eflib.devices import dpu, shp2


@dataclass(frozen=True, kw_only=True)
class EcoflowSwitchEntityDescription[T: DeviceBase](SwitchEntityDescription):
    set_state: Callable[[T, bool], Awaitable] | None = None
    availability_prop: str | None = None


DEPRECATED_SWITCH_TYPES = [
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

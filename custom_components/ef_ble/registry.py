"""Compatibility helpers for Home Assistant device-registry lookups."""

from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry


def async_get_device(
    registry: DeviceRegistry,
    *,
    identifiers: set[tuple[str, str]] | None = None,
    connections: set[tuple[str, str]] | None = None,
    config_entry_id: str | None = None,
) -> DeviceEntry | None:
    """Return the first device matching the supplied identifiers or connections."""
    if (get_devices := getattr(registry, "async_get_devices", None)) is not None:
        devices = get_devices(
            identifiers=identifiers,
            connections=connections,
            config_entry_id=config_entry_id,
        )
        return devices[0] if devices else None

    return registry.async_get_device(identifiers=identifiers, connections=connections)

"""
Move a configured device's registry entries over to a replacement unit

Every entity of this integration has the unique ID `ef_{serial}_{key}`, and the device is
identified by its Bluetooth address (`(DOMAIN, address)`, with `{address}_battery_{n}`
for the extra batteries). A replacement unit has a new serial number and address, so a
plain re-add would create a second set of entities and leave the old history behind.
Rewriting the identities of the existing entries instead keeps the entity IDs, so the
history, statistics, dashboards and automations carry over to the new unit.

The work is split in two so the checks can all run before anything is changed: `plan`
raises `ReplaceError` for anything that would make the move fail or lose data, and
`apply` then makes the changes, undoing the ones already made if one of them fails.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH

from .const import DOMAIN
from .eflib.logging_util import ConnectionLog

_LOGGER = logging.getLogger(__name__)

CONF_LOCAL_NAME = "local_name"


class ReplaceError(Exception):
    """A replacement can't go ahead; `reason` is an abort reason from the strings"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class DeviceChange:
    """New identity of one device registry entry"""

    device_id: str
    old_identifiers: frozenset[tuple[str, str]]
    new_identifiers: frozenset[tuple[str, str]]
    old_connections: frozenset[tuple[str, str]]
    new_connections: frozenset[tuple[str, str]]
    old_serial: str | None
    new_serial: str | None


@dataclass(frozen=True, slots=True)
class ReplacePlan:
    """Everything `apply` will change, worked out and checked beforehand"""

    old_address: str
    new_address: str
    old_serial: str
    new_serial: str
    entity_unique_ids: dict[str, tuple[str, str]] = field(default_factory=dict)
    """entity_id -> (old unique ID, new unique ID)"""
    devices: tuple[DeviceChange, ...] = ()


def old_unit_serial(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Serial number of the unit the entry is set up for, from its device entry"""
    device = _main_device(hass, entry)
    return device.serial_number if device is not None else None


def _main_device(hass: HomeAssistant, entry: ConfigEntry) -> dr.DeviceEntry | None:
    return dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, entry.data[CONF_ADDRESS])},
    )


def _moved(identifier: str, old_address: str, new_address: str) -> str | None:
    """Identifier of the unit or one of its batteries with the address replaced"""
    if identifier == old_address or identifier.startswith(f"{old_address}_battery_"):
        return new_address + identifier[len(old_address) :]
    return None


def plan(
    hass: HomeAssistant,
    entry: ConfigEntry,
    new_address: str,
    new_serial: str,
    other_entries: Iterable[str] = (),
) -> ReplacePlan:
    """
    Work out the move and refuse anything that would clash

    `other_entries` are the addresses already configured as other entries. Raises
    `ReplaceError` with one of these reasons:

    - `old_unit_unknown`: the entry's device has no serial number to move from
    - `same_unit`: the replacement is at the old unit's own address
    - `already_configured`: the replacement is already set up as an entry
    - `device_conflict`: a device with the replacement's identity is in the registry
    - `entity_conflict`: an entity with a new unique ID is in the registry
    """
    old_address = entry.data[CONF_ADDRESS]
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    main_device = _main_device(hass, entry)
    if main_device is None or not main_device.serial_number:
        raise ReplaceError("old_unit_unknown")
    old_serial = main_device.serial_number

    # A replacement can keep the old unit's serial number (EcoFlow re-flashed it); then
    # the entities keep their unique IDs and only the address changes
    if new_address == old_address:
        raise ReplaceError("same_unit")
    if new_address in set(other_entries):
        raise ReplaceError("already_configured")

    devices = []
    for device in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
        identifiers = {
            (domain, moved)
            for domain, ident in device.identifiers
            if domain == DOMAIN
            and (moved := _moved(ident, old_address, new_address)) is not None
        }
        if not identifiers:
            continue
        taken = device_reg.async_get_device(identifiers=identifiers)
        if taken is not None and taken.id != device.id:
            raise ReplaceError("device_conflict")
        is_main = device.id == main_device.id
        devices.append(
            DeviceChange(
                device_id=device.id,
                old_identifiers=frozenset(device.identifiers),
                new_identifiers=frozenset(
                    (domain, ident)
                    for domain, ident in device.identifiers
                    if domain != DOMAIN
                )
                | frozenset(identifiers),
                old_connections=frozenset(device.connections),
                new_connections=(
                    frozenset({(CONNECTION_BLUETOOTH, new_address)})
                    if is_main
                    else frozenset(device.connections)
                ),
                old_serial=device.serial_number,
                new_serial=new_serial if is_main else device.serial_number,
            )
        )

    old_prefix, new_prefix = f"ef_{old_serial}_", f"ef_{new_serial}_"
    entity_unique_ids: dict[str, tuple[str, str]] = {}
    for entity in er.async_entries_for_config_entry(entity_reg, entry.entry_id):
        if old_serial == new_serial:
            break
        if not entity.unique_id.startswith(old_prefix):
            continue
        new_unique_id = new_prefix + entity.unique_id[len(old_prefix) :]
        if entity_reg.async_get_entity_id(entity.domain, DOMAIN, new_unique_id):
            raise ReplaceError("entity_conflict")
        entity_unique_ids[entity.entity_id] = (entity.unique_id, new_unique_id)

    return ReplacePlan(
        old_address=old_address,
        new_address=new_address,
        old_serial=old_serial,
        new_serial=new_serial,
        entity_unique_ids=entity_unique_ids,
        devices=tuple(devices),
    )


def apply(
    hass: HomeAssistant,
    entry: ConfigEntry,
    replace_plan: ReplacePlan,
    *,
    title: str,
    local_name: str | None,
) -> None:
    """
    Make the changes of a plan; the entry must not be loaded

    Raises `ReplaceError("replace_failed")` after undoing what was changed if one of the
    registry updates fails. The entry itself is updated last, so a failure never leaves
    it pointing at the new unit with the old identities.
    """
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    undo: list[tuple[str, object]] = []

    try:
        for entity_id, (
            old_unique_id,
            new_unique_id,
        ) in replace_plan.entity_unique_ids.items():
            entity_reg.async_update_entity(entity_id, new_unique_id=new_unique_id)
            undo.append(("entity", (entity_id, old_unique_id)))
        for change in replace_plan.devices:
            device_reg.async_update_device(
                change.device_id,
                new_identifiers=set(change.new_identifiers),
                new_connections=set(change.new_connections),
                serial_number=change.new_serial,
            )
            undo.append(("device", change))
        data = {**entry.data, CONF_ADDRESS: replace_plan.new_address}
        data[CONF_LOCAL_NAME] = local_name
        hass.config_entries.async_update_entry(
            entry, unique_id=replace_plan.new_address, title=title, data=data
        )
    except Exception as err:
        _LOGGER.exception("Replacing the device failed, undoing the changes")
        _undo(hass, undo)
        raise ReplaceError("replace_failed") from err

    ConnectionLog.clean_cache_for(replace_plan.old_address)


def _undo(hass: HomeAssistant, done: list[tuple[str, object]]) -> None:
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    for kind, item in reversed(done):
        try:
            if kind == "entity":
                entity_id, old_unique_id = item  # type: ignore[misc]
                entity_reg.async_update_entity(entity_id, new_unique_id=old_unique_id)
            else:
                change: DeviceChange = item  # type: ignore[assignment]
                device_reg.async_update_device(
                    change.device_id,
                    new_identifiers=set(change.old_identifiers),
                    new_connections=set(change.old_connections),
                    serial_number=change.old_serial,
                )
        except Exception:
            _LOGGER.exception("Could not undo a registry change")

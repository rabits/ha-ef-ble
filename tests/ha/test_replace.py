"""Tests of the replace-device registry move against real registries"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.ef_ble import config_flow, replace
from custom_components.ef_ble.config_flow import EFBLEConfigFlow
from custom_components.ef_ble.const import DOMAIN

OLD_ADDRESS, NEW_ADDRESS = "AA:BB:CC:00:00:01", "AA:BB:CC:00:00:02"
OLD_SERIAL, NEW_SERIAL = "R651OLDOLDOLD001", "R651NEWNEWNEW002"


@pytest.fixture
async def hass(tmp_path: Path) -> AsyncIterator[HomeAssistant]:
    hass = HomeAssistant(str(tmp_path))
    hass.config.config_dir = str(tmp_path)
    hass.config_entries = ConfigEntries(hass, {})
    await dr.async_load(hass)
    await er.async_load(hass)
    yield hass
    await hass.async_stop(force=True)


def _entry(hass: HomeAssistant, address: str, unique_id: str | None = None):
    entry = ConfigEntry(
        version=1,
        minor_version=3,
        domain=DOMAIN,
        title="EF device",
        data={CONF_ADDRESS: address, "user_id": "1", "local_name": "old"},
        source="user",
        unique_id=unique_id or address,
        options={},
        discovery_keys={},
        subentries_data=None,
    )
    hass.config_entries._entries[entry.entry_id] = entry
    return entry


def _populate(hass: HomeAssistant, entry: ConfigEntry, address, serial):
    device_reg, entity_reg = dr.async_get(hass), er.async_get(hass)
    main = device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, address)},
        connections={(dr.CONNECTION_BLUETOOTH, address)},
        serial_number=serial,
        name="main",
    )
    battery = device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{address}_battery_1")},
        via_device=(DOMAIN, address),
        name="battery",
    )
    for domain, key in (("sensor", "battery_level"), ("switch", "ac_ports")):
        entity_reg.async_get_or_create(
            domain,
            DOMAIN,
            f"ef_{serial}_{key}",
            config_entry=entry,
            device_id=main.id,
        )
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"ef_{serial}_battery_1_voltage",
        config_entry=entry,
        device_id=battery.id,
    )
    return main, battery


async def test_plan_and_apply_move_everything(hass: HomeAssistant) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    main, battery = _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    entity_reg = er.async_get(hass)
    entity_ids = {
        e.entity_id
        for e in er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    }

    result = replace.plan(hass, entry, NEW_ADDRESS, NEW_SERIAL)
    assert result.old_serial == OLD_SERIAL
    assert len(result.entity_unique_ids) == 3

    replace.apply(hass, entry, result, title="EF new", local_name="new")

    # the same entities, now with the new unit's unique IDs
    after = er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    assert {e.entity_id for e in after} == entity_ids
    assert all(e.unique_id.startswith(f"ef_{NEW_SERIAL}_") for e in after)

    # the same devices, now identified by the new address and serial
    device_reg = dr.async_get(hass)
    moved_main = device_reg.async_get(main.id)
    assert moved_main is not None
    assert moved_main.serial_number == NEW_SERIAL
    assert (DOMAIN, NEW_ADDRESS) in moved_main.identifiers
    assert (DOMAIN, OLD_ADDRESS) not in moved_main.identifiers
    assert (dr.CONNECTION_BLUETOOTH, NEW_ADDRESS) in {
        (kind, value.upper()) for kind, value in moved_main.connections
    }
    moved_battery = device_reg.async_get(battery.id)
    assert moved_battery is not None
    assert moved_battery.identifiers == {(DOMAIN, f"{NEW_ADDRESS}_battery_1")}
    assert moved_battery.via_device_id == main.id

    # and the entry follows
    assert entry.unique_id == NEW_ADDRESS
    assert entry.title == "EF new"
    assert entry.data[CONF_ADDRESS] == NEW_ADDRESS
    assert entry.data["local_name"] == "new"
    assert entry.data["user_id"] == "1"


async def test_plan_refuses_the_same_address(hass: HomeAssistant) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    with pytest.raises(replace.ReplaceError) as err:
        replace.plan(hass, entry, OLD_ADDRESS, NEW_SERIAL)
    assert err.value.reason == "same_unit"


async def test_replacement_with_the_same_serial_only_changes_the_address(
    hass: HomeAssistant,
) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    main, battery = _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    entity_reg = er.async_get(hass)
    before = {
        e.entity_id: e.unique_id
        for e in er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    }

    result = replace.plan(hass, entry, NEW_ADDRESS, OLD_SERIAL)
    assert result.entity_unique_ids == {}
    replace.apply(hass, entry, result, title="EF new", local_name="new")

    after = {
        e.entity_id: e.unique_id
        for e in er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    }
    assert after == before
    device_reg = dr.async_get(hass)
    moved = device_reg.async_get(main.id)
    assert moved is not None
    assert moved.serial_number == OLD_SERIAL
    assert (DOMAIN, NEW_ADDRESS) in moved.identifiers
    assert (DOMAIN, OLD_ADDRESS) not in moved.identifiers
    moved_battery = device_reg.async_get(battery.id)
    assert moved_battery is not None
    assert moved_battery.identifiers == {(DOMAIN, f"{NEW_ADDRESS}_battery_1")}
    assert entry.data[CONF_ADDRESS] == NEW_ADDRESS
    assert entry.unique_id == NEW_ADDRESS


async def test_plan_refuses_configured_new_unit(hass: HomeAssistant) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    with pytest.raises(replace.ReplaceError) as err:
        replace.plan(hass, entry, NEW_ADDRESS, NEW_SERIAL, other_entries=[NEW_ADDRESS])
    assert err.value.reason == "already_configured"


async def test_plan_refuses_existing_new_device_and_entities(
    hass: HomeAssistant,
) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    other = _entry(hass, NEW_ADDRESS)
    _populate(hass, other, NEW_ADDRESS, NEW_SERIAL)
    with pytest.raises(replace.ReplaceError) as err:
        replace.plan(hass, entry, NEW_ADDRESS, NEW_SERIAL)
    assert err.value.reason == "device_conflict"

    # an orphaned entity alone is also a conflict
    device_reg = dr.async_get(hass)
    for ident in (NEW_ADDRESS, f"{NEW_ADDRESS}_battery_1"):
        device = device_reg.async_get_device(identifiers={(DOMAIN, ident)})
        assert device is not None
        device_reg.async_remove_device(device.id)
    er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"ef_{NEW_SERIAL}_battery_level"
    )
    with pytest.raises(replace.ReplaceError) as err:
        replace.plan(hass, entry, NEW_ADDRESS, NEW_SERIAL)
    assert err.value.reason == "entity_conflict"


async def test_plan_refuses_unknown_old_unit(hass: HomeAssistant) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    with pytest.raises(replace.ReplaceError) as err:
        replace.plan(hass, entry, NEW_ADDRESS, NEW_SERIAL)
    assert err.value.reason == "old_unit_unknown"


async def test_apply_undoes_changes_when_a_step_fails(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    main, _ = _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    result = replace.plan(hass, entry, NEW_ADDRESS, NEW_SERIAL)

    def fail(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(hass.config_entries, "async_update_entry", fail)

    with pytest.raises(replace.ReplaceError) as err:
        replace.apply(hass, entry, result, title="x", local_name=None)
    assert err.value.reason == "replace_failed"

    entity_reg = er.async_get(hass)
    after = er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    assert all(e.unique_id.startswith(f"ef_{OLD_SERIAL}_") for e in after)
    restored = dr.async_get(hass).async_get(main.id)
    assert restored is not None
    assert restored.serial_number == OLD_SERIAL
    assert (DOMAIN, OLD_ADDRESS) in restored.identifiers
    assert entry.data[CONF_ADDRESS] == OLD_ADDRESS


class _NewUnit:
    address = NEW_ADDRESS
    serial_number = NEW_SERIAL
    name = "EF new"
    device = "River 3"


def _flow(hass: HomeAssistant, entry: ConfigEntry):
    flow = EFBLEConfigFlow()
    flow.hass = hass
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    flow._replace_entry_id = entry.entry_id
    flow._discovered_device = _NewUnit()
    flow._local_names[NEW_ADDRESS] = "new"
    return flow


async def test_flow_menu_offers_settings_and_replace(hass: HomeAssistant) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    result = await _flow(hass, entry).async_step_reconfigure()
    assert result["type"] == "menu"
    assert result["menu_options"] == ["reconfigure_settings", "replace_device"]


async def test_flow_replace_moves_entry_and_reloads(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    reloaded: list[str] = []
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", reloaded.append)

    flow = _flow(hass, entry)
    result = await flow._async_finish_replace()

    assert result["type"] == "abort"
    assert result["reason"] == "replace_successful"
    assert reloaded == [entry.entry_id]
    assert entry.data[CONF_ADDRESS] == NEW_ADDRESS
    # a repeated call (the frontend can refresh the step) changes nothing more
    again = await flow._async_finish_replace()
    assert again["reason"] == "replace_successful"
    assert reloaded == [entry.entry_id]


async def test_flow_replace_aborts_without_changes_on_conflict(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    other = _entry(hass, NEW_ADDRESS)
    reloaded: list[str] = []
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", reloaded.append)

    result = await _flow(hass, entry)._async_finish_replace()

    assert other.entry_id != entry.entry_id
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert reloaded == []
    assert entry.data[CONF_ADDRESS] == OLD_ADDRESS


class _Same(_NewUnit):
    """Stands in for the old unit's device class"""

    def with_packet_version(self, *_):
        return self

    def with_diagnostics_on_exception(self, *_):
        return self

    def with_connection_options(self, *_):
        return self


class _Other(_NewUnit):
    address = "AA:BB:CC:00:00:03"
    serial_number = "R653OTHEROTHER003"


class _Adv:
    local_name = None


class _Info:
    def __init__(self, address: str) -> None:
        self.address = address
        self.device = address
        self.advertisement = _Adv()


async def test_flow_picker_lists_only_new_units_of_the_same_model(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    configured = _entry(hass, "AA:BB:CC:00:00:09")

    units = {
        NEW_ADDRESS: _Same(),  # a new unit of the same model (here with the old serial)
        OLD_ADDRESS: _Same(),  # the old unit itself, already configured
        _Other.address: _Other(),  # another model
        configured.data[CONF_ADDRESS]: _Same(),  # configured as another entry
    }
    units[NEW_ADDRESS].serial_number = OLD_SERIAL
    units[OLD_ADDRESS].address = OLD_ADDRESS
    units[OLD_ADDRESS].serial_number = OLD_SERIAL
    units[configured.data[CONF_ADDRESS]].address = configured.data[CONF_ADDRESS]
    units[configured.data[CONF_ADDRESS]].serial_number = "R651CONFCONFCONF"

    monkeypatch.setattr(
        config_flow,
        "async_discovered_service_info",
        lambda _hass: [_Info(address) for address in units],
    )
    monkeypatch.setattr(
        config_flow.eflib, "NewDevice", lambda device, _adv: units[device]
    )
    monkeypatch.setattr(config_flow.eflib, "device_class_from_sn", lambda _sn: _Same)
    monkeypatch.setattr(config_flow.eflib, "is_unsupported", lambda _device: False)

    result = await _flow(hass, entry).async_step_replace_device()

    assert result["type"] == "form"
    assert result["step_id"] == "replace_device"
    choices = list(result["data_schema"].schema[CONF_ADDRESS].container)
    assert len(choices) == 1
    assert NEW_ADDRESS in choices[0]


async def test_flow_picker_aborts_when_nothing_matches(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    monkeypatch.setattr(config_flow, "async_discovered_service_info", lambda _h: [])
    monkeypatch.setattr(config_flow.eflib, "device_class_from_sn", lambda _sn: _Same)

    result = await _flow(hass, entry).async_step_replace_device()

    assert result["type"] == "abort"
    assert result["reason"] == "no_matching_devices"


async def test_flow_confirm_tests_the_login_with_the_entrys_user_id(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    flow = _flow(hass, entry)
    flow._discovered_device = _Same()
    started: list[str] = []

    async def start(_user_input, origin):
        started.append(origin)
        return {"type": "progress"}

    monkeypatch.setattr(flow, "_async_start_connection", start)
    monkeypatch.setattr(
        flow, "_store", type("S", (), {"async_load": _none}), raising=False
    )

    shown = await flow.async_step_replace_confirm()
    assert shown["type"] == "form"
    assert shown["step_id"] == "replace_confirm"

    # without the backup box ticked nothing starts
    refused = await flow.async_step_replace_confirm({"backup_confirmed": False})
    assert refused["type"] == "form"
    assert refused["errors"] == {"base": "backup_not_confirmed"}
    assert started == []

    await flow.async_step_replace_confirm({"backup_confirmed": True})
    assert started == ["replace_confirm"]
    assert flow._user_id == "1"


async def _none():
    return None


async def test_flow_picker_abort_says_why_units_were_skipped(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)

    other = _Other()
    units = {_Other.address: other}
    monkeypatch.setattr(
        config_flow,
        "async_discovered_service_info",
        lambda _hass: [_Info(address) for address in units],
    )
    monkeypatch.setattr(
        config_flow.eflib, "NewDevice", lambda device, _adv: units[device]
    )
    monkeypatch.setattr(config_flow.eflib, "device_class_from_sn", lambda _sn: _Same)
    monkeypatch.setattr(config_flow.eflib, "is_unsupported", lambda _device: False)

    result = await _flow(hass, entry).async_step_replace_device()

    assert result["type"] == "abort"
    assert result["reason"] == "no_matching_devices"
    skipped = result["description_placeholders"]["skipped"]
    assert f"{_Other.address}: River 3, a different model" in skipped


async def test_flow_confirm_mentions_a_kept_serial_number(hass: HomeAssistant) -> None:
    entry = _entry(hass, OLD_ADDRESS)
    _populate(hass, entry, OLD_ADDRESS, OLD_SERIAL)
    flow = _flow(hass, entry)
    flow._discovered_device = _Same()
    flow._discovered_device.serial_number = OLD_SERIAL
    flow._store = type("S", (), {"async_load": _none})

    shown = await flow.async_step_replace_confirm()
    assert "same serial number" in shown["description_placeholders"]["note"]

    flow._discovered_device.serial_number = NEW_SERIAL
    shown = await flow.async_step_replace_confirm()
    assert shown["description_placeholders"]["note"] == ""

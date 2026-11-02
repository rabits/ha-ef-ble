"""Read-only BLE diagnostics for the EcoFlow DELTA 2 battery management system"""

import sys
from pathlib import Path
from types import ModuleType


def _expose_eflib() -> None:
    """
    Make `custom_components.ef_ble.eflib` importable without Home Assistant

    A normal import runs the integration's `__init__`, which needs Home Assistant.
    Stand-in package modules skip it, the same way `tests/eflib/conftest.py` does.
    """
    if "custom_components.ef_ble" in sys.modules:
        return

    root = Path(__file__).resolve().parents[1] / "custom_components"
    custom_components = ModuleType("custom_components")
    custom_components.__path__ = [str(root)]
    ef_ble = ModuleType("custom_components.ef_ble")
    ef_ble.__path__ = [str(root / "ef_ble")]
    setattr(custom_components, "ef_ble", ef_ble)
    sys.modules["custom_components"] = custom_components
    sys.modules["custom_components.ef_ble"] = ef_ble


_expose_eflib()

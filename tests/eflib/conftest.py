"""Pytest configuration for testing eflib without Home Assistant dependencies."""

import sys
from pathlib import Path
from types import ModuleType

# Create minimal stub modules for custom_components and ef_ble - This prevents their
# __init__.py files from being executed
custom_components = ModuleType("custom_components")
custom_components.__path__ = []
sys.modules["custom_components"] = custom_components

ef_ble = ModuleType("custom_components.ef_ble")
ef_ble.__path__ = [str(Path(__file__).parents[2] / "custom_components" / "ef_ble")]
sys.modules["custom_components.ef_ble"] = ef_ble

setattr(custom_components, "ef_ble", ef_ble)

"""Pytest configuration for testing eflib without Home Assistant dependencies."""

import ctypes
import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from pytest_mock import MockerFixture

from .ecdh_vectors import PUBLIC_KEYS

# Create minimal stub modules for custom_components and ef_ble - This prevents their
# __init__.py files from being executed
custom_components = ModuleType("custom_components")
custom_components.__path__ = []
sys.modules["custom_components"] = custom_components

ef_ble = ModuleType("custom_components.ef_ble")
ef_ble.__path__ = [str(Path(__file__).parents[2] / "custom_components" / "ef_ble")]
sys.modules["custom_components.ef_ble"] = ef_ble

setattr(custom_components, "ef_ble", ef_ble)


@pytest.fixture
def libcrypto() -> ctypes.CDLL:
    # Import after the package stubs, and only for tests that use native ECDH.
    ecdh = importlib.import_module("custom_components.ef_ble.eflib.ecdh")
    return ecdh._load_libcrypto()


@pytest.fixture
def fixed_ecdh_key(
    mocker: MockerFixture, libcrypto: ctypes.CDLL
) -> Callable[[int], None]:
    # These tests import fixed private keys in SEC1 format. Production code never
    # imports or exports private scalars. The test scalars are public and are not
    # real credentials.
    byte_pointer = ctypes.POINTER(ctypes.c_ubyte)
    decoder = libcrypto.d2i_AutoPrivateKey_ex
    decoder.restype = ctypes.c_void_p
    decoder.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(byte_pointer),
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.c_char_p,
    ]

    def set_scalar(scalar: int) -> None:
        encoded = (
            bytes.fromhex("30510201010415")
            + scalar.to_bytes(21, "big")
            + bytes.fromhex("a00706052b81040008a12c032a0004")
            + PUBLIC_KEYS[scalar]
        )

        def generate(_context: int, key_out: object) -> int:
            buffer = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
            cursor = ctypes.cast(buffer, byte_pointer)
            key = decoder(
                None, ctypes.byref(cursor), len(buffer), None, b"provider=default"
            )
            assert key, "OpenSSL rejected the synthetic private-key fixture"
            ctypes.cast(key_out, ctypes.POINTER(ctypes.c_void_p))[0] = key
            return 1

        mocker.patch.object(libcrypto, "EVP_PKEY_generate", side_effect=generate)

    return set_scalar

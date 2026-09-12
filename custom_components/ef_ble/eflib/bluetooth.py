"""
The BLE transport: which characteristics carry the protocol, and the host's GATT cache
"""

from collections.abc import Callable
from typing import Literal, Protocol, runtime_checkable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from .exceptions import UnsupportedBluetoothProtocol
from .logging_util import MaskingLogger

# The characteristic pair each protocol generation carries its traffic on
BT_PROTOCOL_UUIDS = {
    "rfcomm": {
        "notify": "00000003-0000-1000-8000-00805f9b34fb",
        "write": "00000002-0000-1000-8000-00805f9b34fb",
    },
    "nordic_uart": {
        "notify": "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
        "write": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    },
}


def find_characteristic(
    client: BleakClient, char_type: Literal["write", "notify"]
) -> BleakGATTCharacteristic:
    """
    Return the characteristic carrying `char_type`, for either protocol generation

    The raise carries what the device does expose, so a caller can tell an unsupported
    device from an empty, and therefore stale, service table.
    """
    for uuids in BT_PROTOCOL_UUIDS.values():
        if (found := client.services.get_characteristic(uuids[char_type])) is not None:
            return found

    raise UnsupportedBluetoothProtocol(
        char_type,
        [
            f"{c.uuid} {c.description} {c.properties}"
            for c in client.services.characteristics.values()
        ],
    )


async def start_notify(
    client: BleakClient,
    characteristic: BleakGATTCharacteristic,
    callback: Callable,
    *,
    use_bluez_start_notify: bool = False,
) -> None:
    """Subscribe, optionally letting BlueZ write the CCCD instead of bleak"""
    kwargs = {"bluez": {"use_start_notify": True}} if use_bluez_start_notify else {}
    await client.start_notify(characteristic, callback, **kwargs)


@runtime_checkable
class SupportsCacheClear(Protocol):
    """A client that can drop its cached GATT database; plain `BleakClient` cannot"""

    async def clear_cache(self) -> bool: ...


async def clear_gatt_cache(client: BleakClient | None, logger: MaskingLogger) -> None:
    """
    Drop the host's cached GATT database, so the next connect re-discovers services

    BlueZ can resolve services from a cache that no longer matches the device, and every
    reconnect then reaches the same broken table.
    """
    if not isinstance(client, SupportsCacheClear):
        return

    logger.warning("Clearing GATT cache to force service re-discovery")
    try:
        if not await client.clear_cache():
            # bleak itself can decline, and a caller that believed the cache was gone
            # would keep reconnecting into the same broken table without knowing why
            logger.warning("GATT cache was not cleared; this bleak version declined")
    except BleakError as e:
        logger.warning("Failed to clear GATT cache: %s", e)

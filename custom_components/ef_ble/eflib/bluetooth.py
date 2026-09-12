"""
The BLE transport: which characteristics carry the protocol, and host-stack faults

The fault predicates match on error text, and are deliberately narrow: treating an
ordinary link failure as a host fault only slows a reconnect down.
"""

from collections.abc import Callable
from typing import Literal, Protocol, runtime_checkable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from .exceptions import UnsupportedBluetoothProtocol
from .logging_util import LogOptions, MaskingLogger

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


def is_stale_gatt_object(exc: Exception) -> bool:
    """
    Whether a subscribe failed against a characteristic the host cache invented

    BlueZ also answers `Unlikely error` to a write against a peer that just dropped. A
    clear costs nothing when nothing is cached, and `RemoveDevice` plus a re-discovery
    when something is, which is the case worth paying for: both forms came back from a
    host that was genuinely holding a dead handle.
    """
    text = str(exc).lower()
    return "unknownobject" in text or "unlikely error" in text


def is_empty_service_table(exc: Exception) -> bool:
    """Whether the device resolved no characteristics at all, which no real one does"""
    return isinstance(exc, UnsupportedBluetoothProtocol) and not (
        exc.available_characteristics
    )


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

    try:
        if await client.clear_cache():
            logger.warning(
                "Cleared the GATT cache, the next connect re-discovers services"
            )
        else:
            # An ordinary outcome: nothing was cached for this device to begin with
            logger.log_filtered(
                LogOptions.CONNECTION_DEBUG, "GATT cache clear reported nothing to drop"
            )
    except BleakError as e:
        logger.warning("Failed to clear GATT cache: %s", e)

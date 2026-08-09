"""Choosing which Bluetooth proxy a device is connected through"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from time import monotonic

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothScannerDevice
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_CONNECT_GATE_KEY = f"{DOMAIN}_connect_gate"
_CONNECT_GATE_LAST_KEY = f"{DOMAIN}_connect_gate_last"

# Home Assistant scores connection paths partly on how many connections a proxy already
# has in flight, penalising a busy one by more than its entire signal advantage. Two of
# our devices connecting at once therefore push the second onto a worse proxy for the
# whole session, which is why initial connects are taken one at a time.
_CONNECT_GATE_TIMEOUT = 30.0

_PREFERRED_PROXY_TIMEOUT = 20.0
_PREFERRED_PROXY_POLL = 0.5


def connectable_proxies(hass: HomeAssistant) -> dict[str, str]:
    """
    Map the source of every adapter or proxy that can hold a connection to its name

    The source is what a config entry stores, since a proxy's display name changes with
    its device name in Home Assistant while the source does not.
    """
    return {
        scanner.source: scanner.name or scanner.source
        for scanner in bluetooth.async_current_scanners(hass)
        if scanner.connectable
    }


def _best_connection_path(
    devices: list[BluetoothScannerDevice],
) -> BluetoothScannerDevice | None:
    """
    Rank connection paths the way Home Assistant will when it connects

    Strongest advertisement first, then re-ranked by `habluetooth`'s own scoring, which
    is what penalises a proxy for connections it already has in flight. The scoring call
    belongs to that library, so a version that renames it falls back to plain signal
    strength rather than breaking the connect.
    """
    by_rssi = sorted(devices, key=lambda d: d.advertisement.rssi, reverse=True)
    if len(by_rssi) < 2:
        return by_rssi[0] if by_rssi else None

    rssi_diff = by_rssi[0].advertisement.rssi - by_rssi[1].advertisement.rssi
    try:
        return max(by_rssi, key=lambda d: d.score_connection_path(rssi_diff))
    except AttributeError:
        return by_rssi[0]


async def wait_for_preferred_proxy(
    hass: HomeAssistant, address: str, name: str, source: str
) -> None:
    """
    Hold the connect back until the preferred proxy is the path that would be chosen

    A device cannot be pinned to a proxy from here: Home Assistant re-resolves the path
    when it connects and discards the device object we hand it. What we do control is
    *when* we connect, and a proxy that is present, idle and closest wins the scoring on
    its own - so waiting for that moment is the one lever available.

    The wait is bounded, and a preference that cannot be honoured is logged rather than
    leaving the device offline.

    Parameters
    ----------
    hass
        Used to look up which proxies can currently reach the device
    address
        Device address, used to ask which proxies can currently reach it
    name
        Device name, only for logging
    source
        Identifier of the preferred scanner, as stored by the config entry
    """
    if bluetooth.async_scanner_by_source(hass, source) is None:
        _LOGGER.warning(
            "%s: preferred proxy %s is not registered - connecting through any proxy",
            name,
            source,
        )
        return

    started = monotonic()
    deadline = started + _PREFERRED_PROXY_TIMEOUT
    while True:
        best = _best_connection_path(
            bluetooth.async_scanner_devices_by_address(hass, address, connectable=True)
        )
        if best is not None and best.scanner.source == source:
            if (waited := monotonic() - started) >= _PREFERRED_PROXY_POLL:
                _LOGGER.info(
                    "%s: waited %.1fs for preferred proxy %s to become the best path",
                    name,
                    waited,
                    best.scanner.name,
                )
            return

        if monotonic() >= deadline:
            _LOGGER.warning(
                "%s: preferred proxy did not become the best path within %ss - "
                "connecting through %s instead",
                name,
                _PREFERRED_PROXY_TIMEOUT,
                best.scanner.name if best is not None else "whichever proxy answers",
            )
            return

        await asyncio.sleep(_PREFERRED_PROXY_POLL)


@asynccontextmanager
async def connect_gate(
    hass: HomeAssistant, name: str, settle: float
) -> AsyncGenerator[None]:
    """
    Serialise initial connections so our own devices do not outbid each other

    The wait is bounded: a device whose connection hangs must not keep every other
    device offline, so after the timeout we go ahead and connect anyway and accept
    the contention.

    Parameters
    ----------
    hass
        Holds the gate lock, so that it is shared by every config entry rather than
        being per device
    name
        Device name, used only to log which device is waiting and for how long
    settle
        Seconds to leave between one device connecting and the next one starting,
        giving the proxy time to drop its in-progress count before the next device is
        scored. A device that finds the window already elapsed - the usual case when
        devices are not coming up together - is not delayed at all; `0` disables the
        gate for this device entirely
    """
    if not settle:
        _LOGGER.debug("%s: connection delay disabled, connecting immediately", name)
        yield
        return

    lock: asyncio.Lock = hass.data.setdefault(_CONNECT_GATE_KEY, asyncio.Lock())
    contended = lock.locked()
    started = monotonic()
    acquired = False
    try:
        await asyncio.wait_for(lock.acquire(), _CONNECT_GATE_TIMEOUT)
        acquired = True
        if contended:
            _LOGGER.info(
                "%s: waited %.1fs for another device to finish connecting",
                name,
                monotonic() - started,
            )
    except TimeoutError:
        _LOGGER.warning(
            "%s: another device is still connecting after %ss - connecting anyway",
            name,
            _CONNECT_GATE_TIMEOUT,
        )

    if (
        acquired
        and (last := hass.data.get(_CONNECT_GATE_LAST_KEY)) is not None
        and (remaining := settle - (monotonic() - last)) > 0
    ):
        _LOGGER.info(
            "%s: waiting %.1fs for the previous device's proxy to settle",
            name,
            remaining,
        )
        await asyncio.sleep(remaining)

    try:
        yield
    finally:
        if acquired:
            hass.data[_CONNECT_GATE_LAST_KEY] = monotonic()
            lock.release()

"""Choosing which Bluetooth proxy a device is connected through"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from time import monotonic

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothScannerDevice
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_CONNECT_GATE_KEY = f"{DOMAIN}_connect_gate"
_CONNECT_GATE_LAST_KEY = f"{DOMAIN}_connect_gate_last"
_CONNECT_GATE_DEADLINE_KEY = f"{DOMAIN}_connect_gate_deadline"

_PREFERRED_PROXY_POLL = 0.5
# What `habluetooth` scores an advertisement that carries no signal strength as.
_NO_RSSI = -127
_GATE_WAIT_LOG_AFTER = 0.5


def _gate_timeout(
    connect_timeout: float, settle: float, preference_wait: float
) -> float:
    """
    Bound on how long the device holding the gate may keep the next one waiting

    Home Assistant scores connection paths partly on how many connections a proxy
    already has in flight, penalising a busy one by more than its entire signal
    advantage. Two of our devices connecting at once therefore push the second onto a
    worse proxy for the whole session, which is why connects are taken one at a time.

    The bound covers everything the holder does before its first attempt at the device -
    waiting for a preferred proxy if it has one, settling behind the previous device -
    plus that one attempt. `establish_connection` retries beyond it, but a device that
    did not answer the first time is most likely out of range, and keeping every other
    device offline through its remaining retries costs more than the contention does.

    All three inputs are per-device advanced options, so the bound is the *holder's*,
    applied as a deadline from when it took the gate: a waiter that applied its own
    would stop waiting while a holder configured more generously is still on its first
    attempt, which is the contention this avoids.
    """
    return preference_wait + settle + connect_timeout


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


def _rssi(device: BluetoothScannerDevice) -> int:
    """Signal strength of an advertisement, which need not carry one"""
    return device.advertisement.rssi or _NO_RSSI


def _has_free_slot(device: BluetoothScannerDevice) -> bool:
    """
    Whether Home Assistant would accept this path, or skip it for a busier one

    Scoring is only half of the choice: a proxy with no free connection slot is passed
    over however well it scores, so a helper that ignored that would name a saturated
    proxy as the one about to be used. Both checks are read-only - claiming the slot is
    Home Assistant's to do at connect time - and a scanner that tracks neither reports
    itself as free rather than blocking the connect.
    """
    if (connector := device.scanner.connector) is not None:
        return connector.can_connect()

    try:
        allocations = device.scanner.get_allocations()
    except AttributeError:
        return True

    return allocations is None or allocations.free > 0


def _rssi_diff(devices: list[BluetoothScannerDevice]) -> int:
    """Signal advantage of the strongest path over the next one, as scoring takes it"""
    if len(devices) < 2:
        return 0

    by_rssi = sorted(devices, key=_rssi, reverse=True)
    return _rssi(by_rssi[0]) - _rssi(by_rssi[1])


def _best_connection_path(
    devices: list[BluetoothScannerDevice],
) -> BluetoothScannerDevice | None:
    """
    Name the connection path Home Assistant will pick when it connects

    Strongest advertisement first, then re-ranked by `habluetooth`'s own scoring, which
    is what penalises a proxy for connections it already has in flight, and finally the
    first of those with a slot to spare. Scoring arrived in the same release as slot
    allocations, so where it is missing the ranking is signal strength alone.
    """
    by_rssi = sorted(devices, key=_rssi, reverse=True)
    ranked = by_rssi
    if len(by_rssi) > 1:
        rssi_diff = _rssi_diff(devices)
        with suppress(AttributeError):
            ranked = sorted(
                by_rssi, key=lambda d: d.score_connection_path(rssi_diff), reverse=True
            )

    return next((device for device in ranked if _has_free_slot(device)), None)


async def wait_for_preferred_proxy(
    hass: HomeAssistant, address: str, name: str, source: str, timeout: float
) -> None:
    """
    Hold the connect back until the preferred proxy is the path that would be chosen

    A device cannot be pinned to a proxy from here: Home Assistant re-resolves the path
    when it connects and discards the device object we hand it. What we do control is
    *when* we connect, and a proxy that is present, idle and closest wins the scoring on
    its own - so waiting for that moment is the one lever available.

    Not every preference can be honoured: a proxy that is further from the device than
    another never wins the scoring however long we wait for it, and one that has not come
    back up may take a while or never. The wait is therefore bounded, and a device whose
    preference did not come true is connected through whatever path Home Assistant picks
    rather than left offline.

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
    timeout
        Seconds to wait before connecting through whatever proxy is available
    """
    started = monotonic()
    deadline = started + timeout
    while True:
        paths = bluetooth.async_scanner_devices_by_address(
            hass, address, connectable=True
        )
        best = _best_connection_path(paths)
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
                "%s: preferred proxy %s did not become the best path within %ss - "
                "connecting through %s instead",
                name,
                source,
                timeout,
                best.scanner.name if best is not None else "whichever proxy answers",
            )
            return

        await asyncio.sleep(_PREFERRED_PROXY_POLL)


async def _take_gate(
    hass: HomeAssistant, lock: asyncio.Lock, bound: float, name: str
) -> tuple[bool, float]:
    """
    Wait for the gate, or connect anyway once whoever holds it is out of time

    Whoever is connecting publishes the moment its own bound runs out, so a device
    arriving late into the wait stops when that one is out of time rather than waiting a
    full bound of its own on top. Every device queued behind the same holder therefore
    reaches that deadline in the same iteration of the event loop, and only the first to
    claim it goes ahead: the rest wait again behind the bound it publishes in turn, so
    they connect one at a time rather than all at once, which is the contention the gate
    exists to prevent.

    Returns whether the lock was taken - only whoever took it releases it - and the
    deadline published for the next device to wait on.
    """
    started = monotonic()
    while True:
        deadline = hass.data.get(_CONNECT_GATE_DEADLINE_KEY)
        timeout = max(0.0, deadline - monotonic()) if deadline is not None else bound
        try:
            await asyncio.wait_for(lock.acquire(), timeout)
        except TimeoutError:
            if hass.data.get(_CONNECT_GATE_DEADLINE_KEY) != deadline:
                continue
            _LOGGER.warning(
                "%s: another device is still connecting after %.0fs - "
                "connecting anyway",
                name,
                monotonic() - started,
            )
            return False, _publish_deadline(hass, bound)

        if (waited := monotonic() - started) >= _GATE_WAIT_LOG_AFTER:
            _LOGGER.info(
                "%s: waited %.1fs for another device to finish connecting", name, waited
            )
        return True, _publish_deadline(hass, bound)


def _publish_deadline(hass: HomeAssistant, bound: float) -> float:
    """Tell devices arriving into the wait when the one connecting is out of time"""
    deadline = monotonic() + bound
    hass.data[_CONNECT_GATE_DEADLINE_KEY] = deadline
    return deadline


@asynccontextmanager
async def connect_gate(
    hass: HomeAssistant,
    name: str,
    settle: float,
    connect_timeout: float,
    preference_wait: float = 0.0,
) -> AsyncGenerator[None]:
    """
    Serialise connections so our own devices do not outbid each other

    The wait is bounded: a device whose connection hangs must not keep every other
    device offline, so once the holder's deadline has passed we go ahead and connect
    anyway and accept the contention.

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
    connect_timeout
        The device's configured connection timeout, which sets how long this device may
        hold the gate once it has it
    preference_wait
        How long this device may spend waiting for a preferred proxy, which it may hold
        the gate for on top of its connect
    """
    if not settle:
        _LOGGER.debug("%s: connection delay disabled, connecting immediately", name)
        yield
        return

    lock: asyncio.Lock = hass.data.setdefault(_CONNECT_GATE_KEY, asyncio.Lock())
    bound = _gate_timeout(connect_timeout, settle, preference_wait)
    acquired = False
    entered = False
    published: float | None = None
    # Everything from here on runs inside the `finally` that releases the lock: a setup
    # cancelled mid-settle would otherwise hold the gate for the rest of the HA run and
    # time out every later connect.
    try:
        acquired, published = await _take_gate(hass, lock, bound, name)

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

        entered = True
        yield
    finally:
        # Stamped even when the gate timed out, since that device connected too and the
        # next one still has to settle behind it - but not when the wait itself was
        # cancelled, since that device touched no proxy at all.
        if entered:
            hass.data[_CONNECT_GATE_LAST_KEY] = monotonic()
        # Left alone once a device that gave up on the gate has published a later one,
        # since that is what everyone still waiting is now bounded by.
        if (
            published is not None
            and hass.data.get(_CONNECT_GATE_DEADLINE_KEY) == published
        ):
            hass.data.pop(_CONNECT_GATE_DEADLINE_KEY, None)
        if acquired:
            lock.release()

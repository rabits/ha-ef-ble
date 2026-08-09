"""Choosing which Bluetooth proxy a device is connected through"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from time import monotonic

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

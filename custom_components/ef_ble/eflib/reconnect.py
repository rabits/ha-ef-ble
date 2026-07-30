"""Entity-preserving reconnect task coordination."""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from .devicebase import DeviceBase


class ReconnectManager:
    """Run at most one device-specific reconnect and fall back on failure."""

    def __init__(
        self,
        device: DeviceBase,
        reconnect: Callable[[], Awaitable[None]],
        fallback: Callable[[], None],
        create_task: Callable[[Coroutine[Any, Any, None]], asyncio.Task[None]],
        on_success: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._device = device
        self._reconnect = reconnect
        self._fallback = fallback
        self._create_task = create_task
        self._on_success = on_success
        self._on_error = on_error
        self._task: asyncio.Task[None] | None = None

    def on_disconnect(self, _exc: Exception | type[Exception] | None) -> None:
        """Start one reconnect task, or preserve the default reload behavior."""
        if not self._device.RECONNECT_IN_PLACE:
            self._fallback()
            return
        if self._task is not None and not self._task.done():
            return
        self._device.set_reconnecting(True)
        self._task = self._create_task(self._run())

    async def _run(self) -> None:
        try:
            await self._reconnect()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._device.set_reconnecting(False)
            if self._on_error is not None:
                self._on_error(exc)
            self._fallback()
        else:
            self._device.set_reconnecting(False)
            if self._on_success is not None:
                self._on_success()
        finally:
            self._task = None

    def cancel(self) -> None:
        """Cancel an active reconnect during config-entry unload."""
        if self._task is not None:
            self._device.set_reconnecting(False)
            self._task.cancel()

import asyncio
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from bleak import BleakClient
from bleak.backends.device import BLEDevice

from custom_components.ef_ble.eflib import connection as connection_module
from custom_components.ef_ble.eflib.connection import Connection, ConnectionState

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("dbus-daemon") is None,
    reason="Requires Linux and dbus-daemon",
)


@pytest.fixture
def private_bus() -> Iterator[str]:
    with subprocess.Popen(
        ["dbus-daemon", "--session", "--nofork", "--print-address=1"],
        stdout=subprocess.PIPE,
        text=True,
    ) as daemon:
        try:
            yield daemon.stdout.readline().strip()
        finally:
            daemon.terminate()
            daemon.wait(timeout=5)


async def test_real_dbus_connections_released_after_repeated_drops(
    private_bus: str,
) -> None:
    # Real BlueZ backend and D-Bus sockets; only the radio disconnect is simulated.
    from bleak.backends.bluezdbus.client import (  # noqa: PLC0415 - Linux only
        BleakClientBlueZDBus,
    )
    from dbus_fast.aio import MessageBus  # noqa: PLC0415 - Linux only

    device = BLEDevice("AA:BB:CC:DD:EE:FF", "Test device", {"path": "/test/device"})
    connection = Connection(
        device, "TEST_SERIAL", "TEST_USER", AsyncMock(), AsyncMock()
    )
    buses = []
    baseline = len(list(Path("/proc/self/fd").iterdir()))
    try:
        for _ in range(100):
            bus = await MessageBus(bus_address=private_bus).connect()
            buses.append(bus)
            client = BleakClient(
                device,
                backend=BleakClientBlueZDBus,
                disconnected_callback=connection.disconnected,
            )
            backend = client._backend
            backend._bus = bus
            connection._client = client
            connection._set_state(ConnectionState.AUTHENTICATED)

            # Same sequence as BlueZ's unsolicited-disconnect signal handler.
            backend._is_connected = False
            backend._cleanup_all()
            backend._disconnected_callback()
            await connection._disconnect_client()

            assert not bus.connected
            assert backend._bus is None

        await asyncio.sleep(0)
        assert len(list(Path("/proc/self/fd").iterdir())) == baseline
    finally:
        await connection.disconnect()
        for bus in buses:
            bus.disconnect()
            await bus.wait_for_disconnect()


@pytest.mark.parametrize("failure", [None, EOFError, OSError])
async def test_failed_disconnect_releases_bluez_resources(
    private_bus: str, monkeypatch: pytest.MonkeyPatch, failure: type[Exception] | None
) -> None:
    from bleak.backends.bluezdbus.client import (  # noqa: PLC0415 - Linux only
        BleakClientBlueZDBus,
    )
    from dbus_fast.aio import MessageBus  # noqa: PLC0415 - Linux only

    class FailingBus(MessageBus):
        async def call(self, *args: object, **kwargs: object) -> None:
            if failure is not None:
                raise failure("Broken test transport")
            await asyncio.Event().wait()

    baseline = len(list(Path("/proc/self/fd").iterdir()))
    bus = await FailingBus(bus_address=private_bus).connect()
    device = BLEDevice("AA:BB:CC:DD:EE:FF", "Test device", {"path": "/test/device"})
    connection = Connection(
        device, "TEST_SERIAL", "TEST_USER", AsyncMock(), AsyncMock()
    )
    client = BleakClient(
        device,
        backend=BleakClientBlueZDBus,
        disconnected_callback=connection.disconnected,
    )
    backend = client._backend
    backend._bus = bus
    backend._is_connected = True
    backend.services = Mock()
    remove_watcher = backend._remove_device_watcher = Mock()
    monitor_event = backend._disconnect_monitor_event = asyncio.Event()
    monitor = asyncio.create_task(
        backend._disconnect_monitor(bus, "/test/device", monitor_event)
    )
    connection._client = client
    connection._set_state(ConnectionState.AUTHENTICATED)
    monkeypatch.setattr(connection_module, "DISCONNECT_TIMEOUT", 0.01)

    try:
        await asyncio.wait_for(connection.disconnect(), 1)
        assert not bus.connected
        await asyncio.wait_for(bus.wait_for_disconnect(), 1)
        await asyncio.wait_for(monitor, 1)

        assert not bus.connected
        assert backend._bus is None
        assert not backend.is_connected
        assert backend.services is None
        assert backend._disconnect_monitor_event is None
        remove_watcher.assert_called_once()
        assert connection._disconnected.is_set()
        assert connection._state == ConnectionState.DISCONNECTED
        assert len(list(Path("/proc/self/fd").iterdir())) == baseline
    finally:
        bus.disconnect()
        await bus.wait_for_disconnect()
        monitor_event.set()
        await monitor

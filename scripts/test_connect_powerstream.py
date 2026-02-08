# ruff: noqa: INP001, T201
"""
Standalone BLE test script for PowerStream devices.

Scans for a PowerStream device, connects, authenticates, and prints
live telemetry data. Reuses the integration's device/connection/protobuf
code directly — only replacing HA's discovery layer with bleak's BleakScanner.

Usage:
    uv run python scripts/test_connect_powerstream.py
"""

import asyncio
import logging
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure the project root is on sys.path so `custom_components` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakScanner

from custom_components.ef_ble.eflib.devicebase import DeviceBase
from custom_components.ef_ble.eflib.devices import powerstream
from custom_components.ef_ble.eflib.logging_util import LogOptions

USER_ID = "1671430002271248386"
SCAN_TIMEOUT = 10
CONNECT_TIMEOUT = 30

SENSOR_FIELDS = [
    "pv_power_1",
    "pv_voltage_1",
    "pv_current_1",
    "pv_temperature_1",
    "pv_power_2",
    "pv_voltage_2",
    "pv_current_2",
    "pv_temperature_2",
    "battery_level",
    "battery_power",
    "battery_temperature",
    "grid_power",
    "grid_voltage",
    "grid_current",
    "grid_frequency",
    "inverter_temperature",
]

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
_LOGGER = logging.getLogger(__name__)


def _make_telemetry_callback(field_name: str):
    def _cb(value):
        ts = datetime.now(tz=UTC).strftime("%H:%M:%S")
        print(f"  [{ts}] {field_name:>25s} = {value}", flush=True)

    return _cb


async def scan_for_powerstream():
    _LOGGER.info("Scanning for PowerStream devices (timeout=%ds)...", SCAN_TIMEOUT)

    devices = await BleakScanner.discover(
        timeout=SCAN_TIMEOUT,
        return_adv=True,
    )

    for ble_dev, adv_data in devices.values():
        man_data = adv_data.manufacturer_data.get(DeviceBase.MANUFACTURER_KEY)
        if man_data is None:
            continue

        sn_bytes = man_data[1:17]
        if not sn_bytes.startswith(b"HW51"):
            continue

        sn = sn_bytes.decode("ASCII")
        _LOGGER.info("Found PowerStream: %s (SN=%s)", ble_dev.address, sn)
        return ble_dev, adv_data, sn

    return None


async def main():
    result = await scan_for_powerstream()
    if result is None:
        _LOGGER.error("No PowerStream device found during scan")
        sys.exit(1)

    ble_dev, adv_data, sn = result
    device = powerstream.Device(ble_dev, adv_data, sn)

    log_opts = (
        LogOptions.CONNECTION_DEBUG
        | LogOptions.PACKETS
        | LogOptions.DECRYPTED_PAYLOADS
        | LogOptions.DESERIALIZED_MESSAGES
    )

    # Register callbacks BEFORE connecting so the first heartbeat triggers them.
    # Field._set_value only fires callbacks when values change; if values are set
    # before callbacks exist, subsequent identical values are silently skipped.
    for field in SENSOR_FIELDS:
        device.register_state_update_callback(_make_telemetry_callback(field), field)

    _LOGGER.info("Connecting to %s (timeout=%ds)...", sn, CONNECT_TIMEOUT)
    await (
        device.with_logging_options(log_opts)
        .with_disabled_reconnect()
        .connect(user_id=USER_ID, timeout=CONNECT_TIMEOUT, max_attempts=0)
    )

    state = await device.wait_until_authenticated_or_error(raise_on_error=True)
    _LOGGER.info("Connection state: %s", state)

    _LOGGER.info("Listening for telemetry... Press Ctrl+C to stop.")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        await stop.wait()
    finally:
        _LOGGER.info("Disconnecting...")
        await device.disconnect()
        _LOGGER.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())

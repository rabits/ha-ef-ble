"""Find the station, authenticate and listen, without sending it anything else"""

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Self

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

from custom_components.ef_ble.eflib import (
    NewDevice,
    device_class_from_sn,
    sn_from_advertisement,
)
from custom_components.ef_ble.eflib.connection import ConnectionState
from custom_components.ef_ble.eflib.devices._delta2_base import Delta2Base
from custom_components.ef_ble.eflib.packet import Packet

from .capture import CapturedPacket

# Covers the BLE connect retries plus the auth stages, each bounded by eflib itself
CONNECT_TIMEOUT = 90


class StationError(Exception):
    pass


def mask_serial(sn: str) -> str:
    return f"{sn[:4]}{'*' * len(sn[4:-4])}{sn[-4:]}"


def mask_address(address: str) -> str:
    return f"{address[:5]}:**:**:**:**"


@dataclass(frozen=True)
class FoundStation:
    ble_device: BLEDevice
    advertisement: AdvertisementData
    serial: str

    @property
    def model(self) -> str:
        device = NewDevice(self.ble_device, self.advertisement)
        return device.device if device is not None else "?"

    @property
    def is_delta2_family(self) -> bool:
        device_class = device_class_from_sn(self.serial)
        return device_class is not None and issubclass(device_class, Delta2Base)


def _found(device: BLEDevice, adv: AdvertisementData) -> FoundStation | None:
    if (sn := sn_from_advertisement(adv)) is None:
        return None
    return FoundStation(device, adv, sn.decode("ascii", errors="replace"))


async def scan(timeout: float) -> list[FoundStation]:
    """List every EcoFlow device advertising nearby"""
    try:
        seen = await BleakScanner.discover(timeout=timeout, return_adv=True)
    except BleakError as e:
        raise StationError(f"Bluetooth is not available: {e}") from e
    return [
        station
        for device, adv in seen.values()
        if (station := _found(device, adv)) is not None
    ]


async def find_station(timeout: float, sn_suffix: str | None) -> FoundStation:
    """Return the first DELTA 2 family station whose serial ends with `sn_suffix`"""
    match: FoundStation | None = None

    def is_wanted(device: BLEDevice, adv: AdvertisementData) -> bool:
        nonlocal match
        station = _found(device, adv)
        if station is None or not station.is_delta2_family:
            return False
        if sn_suffix and not station.serial.endswith(sn_suffix):
            return False
        match = station
        return True

    try:
        await BleakScanner.find_device_by_filter(is_wanted, timeout=timeout)
    except BleakError as e:
        raise StationError(f"Bluetooth is not available: {e}") from e

    if match is None:
        raise StationError(
            f"no DELTA 2 station found within {timeout:.0f} s. Check that Bluetooth is "
            "on, the station is nearby and the EcoFlow phone app is not connected to "
            "it over Bluetooth"
        )
    return match


class StationSession:
    """
    Authenticated, listen-only link to one station

    For the DELTA 2 family eflib writes only the key exchange and auth packets; the
    counters let the caller show that nothing else went out after authentication.
    """

    def __init__(
        self,
        station: FoundStation,
        user_id: str,
        on_packet: Callable[[CapturedPacket], None],
    ) -> None:
        device = NewDevice(station.ble_device, station.advertisement)
        if not isinstance(device, Delta2Base):
            raise StationError(
                f"{mask_serial(station.serial)} is not a DELTA 2 station"
            )

        self._device = device.with_disabled_reconnect()
        self._user_id = user_id
        self._on_packet = on_packet
        self._frame = b""
        self._authenticated = False
        self.sent_before_auth = 0
        self.sent_after_auth = 0

        device.on_packet_received(self._remember_frame)
        device.on_packet_parsed(self._handle_packet)
        device.on_data_send(self._count_send)
        device.on_connection_state_change(self._track_auth)

    async def __aenter__(self) -> Self:
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await self._device.connect(user_id=self._user_id, max_attempts=3)
                state, exc = await self._device.wait_until_authenticated_or_error(
                    return_exc=True
                )
        except TimeoutError:
            await self._close()
            raise StationError(
                f"the station did not respond within {CONNECT_TIMEOUT} s"
            ) from None

        if not state.authenticated:
            await self._close()
            raise StationError(_describe_failure(state, exc))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._close()

    @property
    def is_connected(self) -> bool:
        return self._device.is_connected

    async def _close(self) -> None:
        # The link is going away either way; a failed goodbye changes nothing
        with contextlib.suppress(BleakError, TimeoutError):
            await self._device.disconnect()

    def _remember_frame(self, frame: bytes) -> None:
        # eflib reports each frame right before the packet parsed from it
        self._frame = frame

    def _handle_packet(self, packet: Packet) -> None:
        frame, self._frame = self._frame, b""
        self._on_packet(
            CapturedPacket(
                time=datetime.now().astimezone(),
                src=packet.src,
                dst=packet.dst,
                cmd_set=packet.cmd_set,
                cmd_id=packet.cmd_id,
                payload=packet.payload,
                frame=frame,
                valid=not Packet.is_invalid(packet),
            )
        )

    def _count_send(self, data: bytes) -> None:
        if self._authenticated:
            self.sent_after_auth += 1
        else:
            self.sent_before_auth += 1

    def _track_auth(self, state: ConnectionState) -> None:
        if state.authenticated:
            self._authenticated = True


def _describe_failure(
    state: ConnectionState, exc: Exception | type[Exception] | None
) -> str:
    reason = f" ({exc})" if exc else ""
    if state is ConnectionState.ERROR_AUTH_FAILED:
        return (
            f"the station rejected authentication{reason}. Check that the User ID "
            "belongs to the account the station is bound to"
        )
    if state.connection_error:
        return (
            f"could not connect over Bluetooth: {state}{reason}. Disconnect the "
            "EcoFlow phone app from the station and try again"
        )
    return f"the connection ended in state {state}{reason}"

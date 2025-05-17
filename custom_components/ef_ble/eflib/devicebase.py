import abc
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import MAX_CONNECT_ATTEMPTS

from .connection import Connection
from .logging_util import DeviceLogger, LogOptions
from .packet import Packet


class DeviceBase:
    """Device Base"""

    MANUFACTURER_KEY = 0xB5B5

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        self._sn = sn
        # We can't use advertisement name here - it's prone to change to "Ecoflow-dev"
        self._name = self.NAME_PREFIX + self._sn[-4:]
        self._name_by_user = self._name
        self._ble_dev = ble_dev
        self._address = ble_dev.address

        self._logger = DeviceLogger(self)
        self._logging_options = LogOptions(0)

        self._logger.debug(
            "Creating new device: %s (%s)",
            self.device,
            sn,
        )

        self._conn = None
        self._callbacks = set()
        self._callbacks_map = {}
        self._state_update_callbacks: dict[str, set[Callable[[Any], None]]] = (
            defaultdict(set)
        )
        self._update_period = 0
        self._last_updated = 0
        self._props_to_update = set()
        self._wait_until_throttle = 0

    @property
    def device(self):
        return self.__doc__ if self.__doc__ else ""

    @property
    def address(self):
        return self._address

    @property
    def name(self):
        return self._name

    @property
    def name_by_user(self):
        return self._name_by_user

    def isValid(self):
        return self._sn != None

    @property
    def is_connected(self) -> bool:
        return self._conn != None and self._conn.is_connected

    @property
    def connection_state(self):
        return None if self._conn is None else self._conn._state

    def with_update_period(self, period: int):
        self._update_period = period
        return self

    def with_logging_options(self, options: LogOptions):
        self._logger.set_options(options)
        if self._conn is not None:
            self._conn.with_logging_options(options)
        return self

    async def data_parse(self, packet: Packet) -> bool:
        """Function to parse incoming data and trigger sensors update"""
        return False

    async def packet_parse(self, data: bytes):
        """Function to parse packet"""
        return Packet.fromBytes(data)

    async def connect(
        self, user_id: str | None = None, max_attempts: int = MAX_CONNECT_ATTEMPTS
    ):
        if self._conn is None:
            self._conn = Connection(
                self._ble_dev,
                self._sn,
                user_id,
                self.data_parse,
                self.packet_parse,
            ).with_logging_options(self._logger.options)
            self._logger.info("Connecting to %s", self.__doc__)
        elif self._conn._user_id != user_id:
            self._conn._user_id = user_id

        await self._conn.connect(max_attempts=max_attempts)

    async def disconnect(self):
        if self._conn is None:
            self._logger.error("Device has no connection")
            return

        await self._conn.disconnect()

    async def waitConnected(self, timeout: int = 20):
        if self._conn is None:
            self._logger.error("Device has no connection")
            return
        await self._conn.waitConnected(timeout=timeout)

    async def waitDisconnected(self):
        if self._conn is None:
            self._logger.error("Device has no connection")
            return

        await self._conn.waitDisconnected()

    def register_callback(
        self, callback: Callable[[], None], propname: str | None = None
    ) -> None:
        """Register callback, called when Device changes state."""
        if propname is None:
            self._callbacks.add(callback)
        else:
            self._callbacks_map[propname] = self._callbacks_map.get(
                propname, set()
            ).union([callback])

    def remove_callback(
        self, callback: Callable[[], None], propname: str | None = None
    ) -> None:
        """Remove previously registered callback."""
        if propname is None:
            self._callbacks.discard(callback)
        else:
            self._callbacks_map.get(propname, set()).discard(callback)

    def update_callback(self, propname: str) -> None:
        """Find the registered callbacks in the map and then calling the callbacks"""

        self._props_to_update.add(propname)

        if self._update_period != 0:
            now = time.time()
            if now - self._last_updated < self._update_period:
                if self._wait_until_throttle is None:
                    return

                # let first few messages update as soon as they come, otherwise everything
                # would display unknown until first period ends
                if self._wait_until_throttle == 0:
                    self._wait_until_throttle = now + 5
                elif self._wait_until_throttle < now:
                    self._wait_until_throttle = None

            self._last_updated = now

        for prop in self._props_to_update:
            for callback in self._callbacks_map.get(prop, set()):
                callback()

        self._props_to_update.clear()

    def register_state_update_callback(
        self, state_update_callback: Callable[[Any], None], propname: str
    ):
        """Register a callback called that receives value of updated property"""
        self._state_update_callbacks[propname].add(state_update_callback)

    def remove_state_update_calback(
        self, callback: Callable[[Any], None], propname: str
    ):
        """Remove previously registered state update callback"""
        self._state_update_callbacks[propname].discard(callback)

    def update_state(self, propname: str, value: Any):
        """Run callback for updated state"""
        if propname not in self._state_update_callbacks:
            return

        for update in self._state_update_callbacks[propname]:
            update(value)

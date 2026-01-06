import abc
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import MAX_CONNECT_ATTEMPTS

from .connection import Connection, ConnectionState, DisconnectListener
from .logging_util import DeviceLogger, LogOptions
from .packet import Packet


class DeviceBase(abc.ABC):
    """Device Base"""

    MANUFACTURER_KEY = 0xB5B5

    @classmethod
    @abc.abstractmethod
    def check(cls, sn: bytes) -> bool: ...

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        self._sn = sn
        # We can't use advertisement name here - it's prone to change to "Ecoflow-dev"
        self._name = self.NAME_PREFIX + self._sn[-4:]
        self._name_by_user = None
        self._ble_dev = ble_dev
        self._address = ble_dev.address

        self._logger = DeviceLogger(self)
        self._logging_options = LogOptions.no_options()

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

        self._reconnect_disabled = False
        self._disconnect_listeners: list[DisconnectListener] = []

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
    def name_by_user(self) -> str:
        return self._name_by_user if self._name_by_user is not None else self.name

    @property
    def serial_number(self):
        """Full device serial number parsed from manufacturer data."""
        return self._sn

    def isValid(self):
        return self._sn is not None

    @property
    def is_connected(self) -> bool:
        return self._conn is not None and self._conn.is_connected

    @property
    def packet_version(self) -> int:
        return 0x03

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

    def with_disabled_reconnect(self, is_disabled: bool = True):
        self._reconnect_disabled = is_disabled
        if self._conn is not None:
            self._conn.with_disabled_reconnect(is_disabled)
        return self

    async def data_parse(self, packet: Packet) -> bool:
        """Function to parse incoming data and trigger sensors update"""
        return False

    async def packet_parse(self, data: bytes):
        """Function to parse packet"""
        return Packet.fromBytes(data)

    async def connect(
        self,
        user_id: str | None = None,
        max_attempts: int = MAX_CONNECT_ATTEMPTS,
        timeout: int = 20,
    ):
        if self._conn is None:
            self._conn = (
                Connection(
                    self._ble_dev,
                    self._sn,
                    user_id,
                    self.data_parse,
                    self.packet_parse,
                    packet_version=self.packet_version,
                )
                .with_logging_options(self._logger.options)
                .with_disabled_reconnect(self._reconnect_disabled)
            )
            self._logger.info("Connecting to %s", self.device)

            def _disconnect_callback(exc):
                for callback in self._disconnect_listeners:
                    callback(exc)

            self._conn.on_disconnect(listener=_disconnect_callback)
        elif self._conn._user_id != user_id:
            self._conn._user_id = user_id

        await self._conn.connect(max_attempts=max_attempts, timeout=timeout)

    async def disconnect(self):
        if self._conn is None:
            self._logger.error("Device has no connection")
            return

        await self._conn.disconnect()

    async def wait_connected(self, timeout: int = 20):
        if self._conn is None:
            self._logger.error("Device has no connection")
            return
        await self._conn.wait_connected(timeout=timeout)

    async def wait_disconnected(self):
        if self._conn is None:
            self._logger.error("Device has no connection")
            return

        if self.is_connected:
            await self._conn.wait_disconnected()

    async def wait_until_authenticated_or_error(self, raise_on_error: bool = False):
        if self._conn is None:
            return ConnectionState.NOT_CONNECTED

        return await self._conn.wait_until_authenticated_or_error(
            raise_on_error=raise_on_error
        )

    def on_disconnect(self, listener: DisconnectListener):
        """
        Add disconnect listener

        Parameters
        ----------
        listener
            Listener that will be called on disconnect that receives exception as a
            param if one occured before device disconnected

        Return
        -------
        Function to remove this listener
        """
        self._disconnect_listeners.append(listener)

        def _unlisten():
            self._disconnect_listeners.remove(listener)

        return _unlisten

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

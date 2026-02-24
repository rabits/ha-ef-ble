import abc
import asyncio
import time
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, overload

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .connection import (
    Connection,
    ConnectionState,
    ConnectionStateListener,
    DataReceivedListener,
    DataSendListener,
    DisconnectListener,
    PacketParsedListener,
    PacketReceivedListener,
)
from .listeners import ListenerGroup, ListenerRegistry
from .logging_util import (
    ConnectionLog,
    DeviceDiagnosticsCollector,
    DeviceLogger,
    LogOptions,
)
from .packet import Packet
from .props.raw_data_props import Literal


class _Listeners(ListenerRegistry):
    on_packet_received: ListenerGroup[PacketReceivedListener]
    on_disconnect: ListenerGroup[DisconnectListener]
    on_connection_state_change: ListenerGroup[ConnectionStateListener]
    on_packet_parsed: ListenerGroup[PacketParsedListener]
    on_data_received: ListenerGroup[DataReceivedListener]
    on_data_send: ListenerGroup[DataSendListener]


class DeviceBase(abc.ABC):
    """Device Base"""

    MANUFACTURER_KEY = 0xB5B5

    NAME_PREFIX: str

    _listeners = _Listeners.create()

    @classmethod
    @abc.abstractmethod
    def check(cls, sn: bytes) -> bool: ...

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        self._sn = sn
        # We can't use advertisement name here - it's prone to change to "Ecoflow-dev"
        self._default_name = self.NAME_PREFIX + self._sn[-4:]
        self._name = self._default_name
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
        self._connection_event = asyncio.Event()
        self._callbacks = set()
        self._callbacks_map = {}
        self._state_update_callbacks: dict[str, set[Callable[[Any], None]]] = (
            defaultdict(set)
        )
        self._update_period = 0
        self._last_updated = 0
        self._props_to_update = set()
        self._wait_until_throttle = 0
        self._packet_version = 0x03

        self._reconnect_disabled = False
        self._diagnostics = DeviceDiagnosticsCollector(self)

        self._manufacturer_data = adv_data.manufacturer_data[self.MANUFACTURER_KEY]

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
        return self._packet_version

    @property
    def connection_state(self):
        return None if self._conn is None else self._conn._connection_state

    @property
    def diagnostics(self):
        return self._diagnostics

    @cached_property
    def scan_record(self):
        return _ScanRecordV2.from_manufacturer_data(self._manufacturer_data)

    def add_timer_task(
        self,
        coro: Callable[[], Coroutine],
        interval: int = 30,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ):
        def _register_timer_task(state: ConnectionState):
            if state == ConnectionState.AUTHENTICATED:
                self._conn.add_timer_task(coro, interval, event_loop)

        self.on_connection_state_change(_register_timer_task)

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

    def with_packet_version(self, packet_version: int | None = None):
        self._packet_version = (
            packet_version if packet_version is not None else self._packet_version
        )
        return self

    def with_enabled_packet_diagnostics(self, enabled: bool = True):
        self._diagnostics.enabled(enabled)
        return self

    def with_name(self, name: str):
        self._name = name
        return self

    async def data_parse(self, packet: Packet) -> bool:
        """Parse incoming data and trigger sensors update"""
        return False

    async def packet_parse(self, data: bytes):
        """Parse packet"""
        return Packet.fromBytes(data)

    @property
    def connection_log(self):
        if (connection_log := getattr(self, "_connection_log", None)) is not None:
            return connection_log

        self._connection_log = ConnectionLog(self.address.replace(":", "_"))
        return self._connection_log

    async def connect(
        self,
        user_id: str | None = None,
        max_attempts: int | None = None,
        timeout: int = 20,
    ):
        if self._conn is None:
            self._conn = (
                Connection(
                    ble_dev=self._ble_dev,
                    dev_sn=self._sn,
                    user_id=user_id,
                    data_parse=self.data_parse,
                    packet_parse=self.packet_parse,
                    packet_version=self.packet_version,
                    encrypt_type=self.scan_record.encrypt_type,
                )
                .with_logging_options(self._logger.options)
                .with_disabled_reconnect(self._reconnect_disabled)
            )
            self._connection_event.set()

            self._logger.info("Connecting to %s", self.device)

            self._conn.on_disconnect(self._listeners.on_disconnect)
            self._conn.on_packet_data_received(self._listeners.on_packet_received)
            self._conn.on_packet_parsed(self._listeners.on_packet_parsed)
            self._conn.on_state_change(self._listeners.on_connection_state_change)
            self._conn.on_state_change(lambda state: self.connection_log.append(state))
            self._conn.on_data_received(self._listeners.on_data_received)
            self._conn.on_data_send(self._listeners.on_data_send)

        elif self._conn._user_id != user_id:
            self._conn._user_id = user_id

        await self._conn.connect(max_attempts=max_attempts, timeout=timeout)

    async def disconnect(self):
        if self._conn is None:
            self._logger.error("Device has no connection")
            return

        await self._conn.disconnect()
        self._connection_event.clear()
        self._conn = None

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

    @overload
    async def wait_until_authenticated_or_error(
        self, raise_on_error: bool = False, return_exc: Literal[False] = False
    ) -> ConnectionState: ...

    @overload
    async def wait_until_authenticated_or_error(
        self,
        raise_on_error: bool = False,
        return_exc: Literal[True] = True,
    ) -> tuple[ConnectionState, Exception | None]: ...

    async def wait_until_authenticated_or_error(
        self, raise_on_error: bool = False, return_exc: bool = False
    ):
        if self._conn is None:
            return ConnectionState.NOT_CONNECTED

        return await self._conn.wait_until_authenticated_or_error(
            raise_on_error=raise_on_error,
            return_exc=return_exc,
        )

    async def observe_connection(self):
        while self._conn is None:
            yield ConnectionState.NOT_CONNECTED
            await self._connection_event.wait()

        async for state in self._conn.observe_connection():
            yield state

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
        return self._listeners.on_disconnect.add(listener)

    def on_packet_received(self, packet_received_listener: PacketReceivedListener):
        return self._listeners.on_packet_received.add(packet_received_listener)

    def on_packet_parsed(self, packet_parsed_listener: PacketParsedListener):
        return self._listeners.on_packet_parsed.add(packet_parsed_listener)

    def on_data_received(self, listener: DataReceivedListener):
        return self._listeners.on_data_received.add(listener)

    def on_data_send(self, listener: DataSendListener):
        return self._listeners.on_data_send.add(listener)

    def on_connection_state_change(
        self, connection_state_listener: ConnectionStateListener
    ):
        return self._listeners.on_connection_state_change.add(connection_state_listener)

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

                # let first few messages update as soon as they come, otherwise
                # everything would display unknown until first period ends
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


@dataclass
class _ScanRecordV2:
    proto_version: int
    serial_number: str
    status: int
    product_type: int

    capability_flags: int

    encrypt: bool = field(init=False)
    support_verified: bool = field(init=False)
    verified: bool = field(init=False)
    encrypt_type: int = field(init=False)
    support_5g: bool = field(init=False)

    active_flag: bool = field(init=False)

    def __post_init__(self):
        self.encrypt = (self.capability_flags & 0b0000001) != 0
        self.support_verified = (self.capability_flags & 0b0000010) != 0
        self.verified = (self.capability_flags & 0b0000100) != 0
        self.encrypt_type = (self.capability_flags & 0b0111000) >> 3
        self.support_5g = ((self.capability_flags >> 6) & 0b1000000) != 0

        self.active_flag = ((self.status >> 7) & 0x01) == 1

    @classmethod
    def from_manufacturer_data(cls, manufacturer_data: bytes):
        return cls(
            proto_version=manufacturer_data[0],
            serial_number=manufacturer_data[1:17].decode(),
            status=manufacturer_data[17] if len(manufacturer_data) > 17 else 0,
            product_type=manufacturer_data[18] if len(manufacturer_data) > 18 else 0,
            capability_flags=(
                manufacturer_data[22] if len(manufacturer_data) > 19 else 0b0111000
            ),
        )

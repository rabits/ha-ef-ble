import asyncio
import logging
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .connection import Connection
from .packet import Packet

_LOGGER = logging.getLogger(__name__)

class DeviceBase:
    '''Device Base'''
    MANUFACTURER_KEY = 0xb5b5

    def __init__(self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str) -> None:
        _LOGGER.debug("%s: Creating new device: %s '%s' (%s)", ble_dev.address, self.device, adv_data.local_name, sn)
        self._ble_dev = ble_dev
        self._address = ble_dev.address
        self._name = adv_data.local_name
        self._name_by_user = self._name
        self._sn = sn

        self._conn = None
        self._callbacks = set()

    @property
    def device(self):
        return self.__doc__

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

    async def data_parse(self, packet: Packet):
        '''Function to parse incoming data and trigger sensors update'''
        return False

    async def connect(self, user_id: str | None = None):
        if self._conn == None:
            if user_id != None:
                self._user_id = user_id
            self._conn = Connection(self._ble_dev, self._sn, self._user_id, self.data_parse)
        await self._conn.connect()

    async def disconnect(self):
        if self._conn == None:
            _LOGGER.warning("%s: Device is not connected", self._address)
            return

        await self._conn.disconnect()

    async def waitDisconnect(self):
        if self._conn == None:
            _LOGGER.warning("%s: Device is not connected", self._address)
            return

        await self._conn.waitDisconnect()

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Device changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

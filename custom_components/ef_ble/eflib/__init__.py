"""Library for EcoFlow BLE protocol"""

import logging
from types import ModuleType

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .devicebase import DeviceBase
from . import devices

_LOGGER = logging.getLogger(__name__)

def NewDevice(ble_dev: BLEDevice, adv_data: AdvertisementData):
    '''Returns Device if ble dev fits the requirements otherwise None'''
    if not (hasattr(adv_data, "manufacturer_data") and DeviceBase.MANUFACTURER_KEY in adv_data.manufacturer_data):
        return None

    # Looking for device SN
    man_data = adv_data.manufacturer_data[DeviceBase.MANUFACTURER_KEY]
    sn = man_data[1:17]

    # Check if known devices fits the found serial number
    for item in devices.__dict__.values():
        if isinstance(item, ModuleType) and \
                item.__package__.endswith('eflib.devices') and \
                item.Device.check(sn):
            return item.Device(ble_dev, adv_data, sn.decode('ASCII'))

    _LOGGER.warning("%s: Unknown SN: %s", ble_dev.address, sn)
    return None

__all__ = [
    'DeviceBase',
    'NewDevice',
]

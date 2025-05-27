"""Library for EcoFlow BLE protocol"""

import logging
from typing import TypeGuard

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from . import devices
from .devicebase import DeviceBase
from .devices import unsupported

_LOGGER = logging.getLogger(__name__)


def sn_from_advertisement(adv_data: AdvertisementData):
    if not (
        hasattr(adv_data, "manufacturer_data")
        and DeviceBase.MANUFACTURER_KEY in adv_data.manufacturer_data
    ):
        return None

    man_data = adv_data.manufacturer_data[DeviceBase.MANUFACTURER_KEY]
    return man_data[1:17]


def is_unsupported(
    device: DeviceBase | None,
) -> TypeGuard[unsupported.UnsupportedDevice]:
    return isinstance(device, unsupported.UnsupportedDevice)


def NewDevice(ble_dev: BLEDevice, adv_data: AdvertisementData) -> DeviceBase | None:
    """Return Device if ble dev fits the requirements otherwise None"""
    if (sn := sn_from_advertisement(adv_data)) is None:
        return None

    # Check if known devices fits the found serial number
    for item in devices.devices:
        if (device := getattr(item, "Device", None)) is not None and device.check(sn):
            return item.Device(ble_dev, adv_data, sn.decode("ASCII"))

    return unsupported.UnsupportedDevice(ble_dev, adv_data, sn.decode("ASCII"))


__all__ = [
    "DeviceBase",
    "NewDevice",
]

"""Library for EcoFlow BLE protocol"""

from typing import TYPE_CHECKING, TypeGuard

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from . import devices
from .devicebase import DeviceBase
from .devices import powerstream, stream_microinverter, unsupported
from .entity import controls as controls
from .entity import units as units
from .props.updatable_props import UpdatableProps

if TYPE_CHECKING:
    from .props import ProtobufProps, RawDataProps


def sn_from_advertisement(adv_data: AdvertisementData):
    if not (
        hasattr(adv_data, "manufacturer_data")
        and DeviceBase.MANUFACTURER_KEY in adv_data.manufacturer_data
    ):
        return None

    man_data = adv_data.manufacturer_data[DeviceBase.MANUFACTURER_KEY]
    return man_data[1:17].strip(b"\x00")


def is_unsupported(
    device: DeviceBase | None,
) -> TypeGuard[unsupported.UnsupportedDevice]:
    return isinstance(device, unsupported.UnsupportedDevice)


def is_solar_only(device: DeviceBase | None):
    return isinstance(device, (stream_microinverter.Device, powerstream.Device))


def NewDevice(ble_dev: BLEDevice, adv_data: AdvertisementData) -> DeviceBase | None:
    """Return Device if ble dev fits the requirements otherwise None"""
    if (sn := sn_from_advertisement(adv_data)) is None:
        return None

    # Check if known devices fits the found serial number
    for item in devices.devices:
        if (device := getattr(item, "Device", None)) is not None and device.check(sn):
            return item.Device(ble_dev, adv_data, sn.decode("ASCII"))

    return unsupported.UnsupportedDevice(ble_dev, adv_data, sn.decode("ASCII"))


def get_protobuf_device(device: DeviceBase | None) -> "ProtobufProps | None":
    from .props import ProtobufProps  # noqa: PLC0415

    return device if isinstance(device, ProtobufProps) else None


def get_fixed_length_coding_device(device: DeviceBase | None) -> "RawDataProps | None":
    from .props import RawDataProps  # noqa: PLC0415

    return device if isinstance(device, RawDataProps) else None


def get_updatable_prop_device(device: "DeviceBase"):
    if not isinstance(device, UpdatableProps):
        raise TypeError("Device has to be subclass of UpdatableProps")

    return device


def get_controls[E: "controls.ControlType"](
    device: "DeviceBase", control_type: type[E]
) -> list[E]:
    return get_updatable_prop_device(device).get_controls(control_type)


__all__ = [
    "DeviceBase",
    "NewDevice",
    "controls",
    "get_controls",
    "get_fixed_length_coding_device",
    "get_protobuf_device",
    "get_updatable_prop_device",
    "is_solar_only",
    "is_unsupported",
    "units",
]

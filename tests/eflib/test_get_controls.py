"""Tests for `eflib.get_controls` with devices that expose no controls."""

import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble import eflib
from custom_components.ef_ble.eflib.devices.unsupported import UnsupportedDevice
from custom_components.ef_ble.eflib.entity import controls


@pytest.fixture
def unsupported_device(mocker: MockerFixture) -> UnsupportedDevice:
    """A device that does not implement UpdatableProps."""
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    return UnsupportedDevice(ble_dev, adv_data, "TESTSN012345")


@pytest.mark.parametrize(
    "control_type",
    [
        controls.button,
        controls.toggle,
        controls.NumberType,
        controls.select,
        controls.climate,
    ],
)
def test_get_controls_is_empty_for_device_without_props(
    unsupported_device: UnsupportedDevice, control_type
) -> None:
    """
    A device with no UpdatableProps has no controls - and must not raise.

    Raising aborted setup of *every* control platform (button, climate, number,
    select, switch) for that device, so none of its entities were created.
    """
    assert eflib.get_controls(unsupported_device, control_type) == []


def test_get_updatable_prop_device_still_raises(
    unsupported_device: UnsupportedDevice,
) -> None:
    """Callers that genuinely require props keep the explicit error."""
    with pytest.raises(TypeError):
        eflib.get_updatable_prop_device(unsupported_device)

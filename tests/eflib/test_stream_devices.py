from custom_components.ef_ble.eflib.devices import (
    stream_ac,
    stream_ac_pro,
    stream_max,
    stream_microinverter,
    stream_pro,
    stream_ultra,
)


def test_stream_ac_variants_expose_expected_energy_source_fields():
    expected_fields_by_device = {
        stream_ac.Device: {"battery_power"},
        stream_ac_pro.Device: {"battery_power"},
        stream_max.Device: {"battery_power", "pv_power_sum"},
        stream_pro.Device: {"battery_power", "pv_power_sum"},
        stream_ultra.Device: {"battery_power", "pv_power_sum"},
    }

    for device_cls, expected_fields in expected_fields_by_device.items():
        for field_name in expected_fields:
            assert hasattr(device_cls, field_name), (
                f"{device_cls.__doc__} is missing {field_name}"
            )

    assert not hasattr(stream_ac.Device, "pv_power_sum")
    assert not hasattr(stream_ac_pro.Device, "pv_power_sum")


def test_stream_microinverter_exposes_expected_energy_source_fields():
    assert hasattr(stream_microinverter.Device, "pv_power_1")
    assert hasattr(stream_microinverter.Device, "pv_power_2")
    assert not hasattr(stream_microinverter.Device, "battery_power")

"""
Full layout of the DELTA 2 family BMS heartbeat (`cmd_set` 0x20, `cmd_id` 0x32)

The first 69 bytes are eflib's `DirectBmsMDeltaHeartbeatPack`, taken from the
decompiled app. The rest follows the field order of `BMSHeartBeatReport` in
`proto/pd335_bms_bp.proto`, the protobuf twin of this struct on newer models, with
widths fitted to real captures. Arrays are a count byte followed by that many values,
so every offset after `cell_vol` moves with the cell and sensor counts. Signedness
comes from the proto: what is `int32` there is signed here.

`confirmed` marks fields whose position and meaning were cross-checked in captures
(cell extremes against the cell array, `all_err_code` against `err_code`, energy
against charge, capacities against the model's rating).
The others sit at a plausible position, but their width or meaning is a guess.
"""

import struct
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, fields
from typing import Any

BMS_CMD_SET = 0x20
BMS_CMD_ID = 0x32

_LAYOUT = "layout"


@dataclass(frozen=True)
class Layout:
    fmt: str
    unit: str
    label: str
    count: str | None
    confirmed: bool


def _at(
    fmt: str,
    unit: str = "",
    label: str = "",
    *,
    count: str | None = None,
    confirmed: bool = False,
) -> Any:
    layout = Layout(fmt, unit, label, count, confirmed)
    return field(default=None, metadata={_LAYOUT: layout})


@dataclass(frozen=True)
class BmsHeartbeat:
    """
    One decoded heartbeat; a field the payload is too short for stays `None`

    `spans` maps each decoded field to its bytes in the payload, and `tail` holds the
    bytes after the last field this layout knows.
    """

    # Bytes 0-68: `DirectBmsMDeltaHeartbeatPack`
    num: int | None = _at("B", "", "Pack number (0 is the main pack)", confirmed=True)
    type_: int | None = _at("B", "", "BMS type", confirmed=True)
    cell_id: int | None = _at("B", "", "Cell type", confirmed=True)
    err_code: int | None = _at("I", "", "Error code", confirmed=True)
    sys_ver: int | None = _at("I", "", "BMS firmware version", confirmed=True)
    soc: int | None = _at("B", "%", "State of charge (integer)", confirmed=True)
    vol: int | None = _at("I", "mV", "Pack voltage", confirmed=True)
    amp: int | None = _at("i", "mA", "Pack current", confirmed=True)
    temp: int | None = _at("b", "°C", "Pack temperature", confirmed=True)
    open_bms_idx: int | None = _at("B", "", "Enabled packs", confirmed=True)
    design_cap: int | None = _at("I", "mAh", "Design capacity", confirmed=True)
    remain_cap: int | None = _at("I", "mAh", "Remaining capacity", confirmed=True)
    full_cap: int | None = _at("I", "mAh", "Full (actual) capacity", confirmed=True)
    cycles: int | None = _at("I", "", "Charge-discharge cycles", confirmed=True)
    soh: int | None = _at("B", "%", "SOH, state of health", confirmed=True)
    max_cell_vol: int | None = _at("H", "mV", "Max cell voltage", confirmed=True)
    min_cell_vol: int | None = _at("H", "mV", "Min cell voltage", confirmed=True)
    max_cell_temp: int | None = _at("b", "°C", "Max cell temp", confirmed=True)
    min_cell_temp: int | None = _at("b", "°C", "Min cell temp", confirmed=True)
    max_mos_temp: int | None = _at("b", "°C", "Max MOSFET temp", confirmed=True)
    min_mos_temp: int | None = _at("b", "°C", "Min MOSFET temp", confirmed=True)
    bms_fault: int | None = _at("B", "", "Permanent BMS fault", confirmed=True)
    bq_sys_stat_reg: int | None = _at(
        "B", "", "AFE protection register", confirmed=True
    )
    tag_chg_amp: int | None = _at("I", "mA", "Target charge current", confirmed=True)
    f32_show_soc: float | None = _at("f", "%", "Charge shown on screen", confirmed=True)
    input_watts: int | None = _at("I", "W", "Charge power", confirmed=True)
    output_watts: int | None = _at("I", "W", "Discharge power", confirmed=True)
    remain_time: int | None = _at("I", "min", "Time remaining", confirmed=True)

    # Heartbeat 0x0103 (DELTA 2 main pack) ends with `cycle_soh`
    mos_state: int | None = _at("B", "", "MOSFET switch state")
    balance_state: int | None = _at("H", "", "Cell balancing")
    max_vol_diff: int | None = _at("H", "mV", "Cell voltage spread", confirmed=True)
    cell_series_num: int | None = _at("B", "", "Cell count", confirmed=True)
    cell_vol: tuple[int, ...] | None = _at(
        "H", "mV", "Cell voltages", count="cell_series_num", confirmed=True
    )
    cell_ntc_num: int | None = _at("B", "", "Cell temp sensors", confirmed=True)
    cell_temp: tuple[int, ...] | None = _at(
        "h", "°C", "Cell temperatures", count="cell_ntc_num", confirmed=True
    )
    hw_ver: str | None = _at("6s", "", "Board version", confirmed=True)
    bms_heartbeat_ver: int | None = _at("H", "", "Packet format version")
    ecloud_ocv: int | None = _at("H", "", "eCloud OCV")
    bms_sn: str | None = _at("16s", "", "BMS serial number", confirmed=True)
    product_type: int | None = _at("B", "", "Product type")
    product_detail: int | None = _at("B", "", "Product subtype")
    act_soc: float | None = _at("f", "%", "Actual charge", confirmed=True)
    diff_soc: float | None = _at("f", "%", "Charge difference")
    target_soc: float | None = _at("f", "%", "Target charge", confirmed=True)
    sys_loader_ver: int | None = _at("I", "", "Bootloader version", confirmed=True)
    sys_state: int | None = _at("B", "", "System state")
    chg_dsg_state: int | None = _at("B", "", "Charge/discharge state")
    all_err_code: int | None = _at("I", "", "All error codes (bits)", confirmed=True)
    all_bms_fault: int | None = _at("I", "", "All faults (bits)")
    accu_chg_cap: int | None = _at("I", "mAh", "Lifetime charged")
    accu_dsg_cap: int | None = _at("I", "mAh", "Lifetime discharged")
    real_soh: float | None = _at("f", "%", "Actual SOH")
    calendar_soh: float | None = _at("f", "%", "Calendar SOH")
    cycle_soh: float | None = _at("f", "%", "Cycle SOH")

    # Heartbeat 0x0106 (seen from a DELTA 3 extra battery) carries the rest
    mos_ntc_num: int | None = _at("B", "", "MOSFET temp sensors", confirmed=True)
    mos_temp: tuple[int, ...] | None = _at(
        "h", "°C", "MOSFET temperatures", count="mos_ntc_num", confirmed=True
    )
    env_ntc_num: int | None = _at("B", "", "Ambient temp sensors", confirmed=True)
    env_temp: tuple[int, ...] | None = _at(
        "h", "°C", "Ambient temperatures", count="env_ntc_num", confirmed=True
    )
    heatfilm_ntc_num: int | None = _at("B", "", "Heater temp sensors")
    heatfilm_temp: tuple[int, ...] | None = _at(
        "h", "°C", "Heater temperatures", count="heatfilm_ntc_num"
    )
    cur_sensor_ntc_num: int | None = _at("B", "", "Shunt temp sensors", confirmed=True)
    cur_sensor_temp: tuple[int, ...] | None = _at(
        "h", "°C", "Shunt temperatures", count="cur_sensor_ntc_num", confirmed=True
    )
    max_env_temp: int | None = _at("h", "°C", "Max ambient temp", confirmed=True)
    min_env_temp: int | None = _at("h", "°C", "Min ambient temp", confirmed=True)
    max_heatfilm_temp: int | None = _at("h", "°C", "Max heater temp")
    min_heatfilm_temp: int | None = _at("h", "°C", "Min heater temp")
    max_cur_sensor_temp: int | None = _at("h", "°C", "Max shunt temp", confirmed=True)
    min_cur_sensor_temp: int | None = _at("h", "°C", "Min shunt temp", confirmed=True)
    balance_cmd: int | None = _at("I", "", "Balancing command")
    remain_balance_time: tuple[int, ...] | None = _at(
        "H", "", "Balancing time left", count="cell_series_num"
    )
    afe_sys_status: int | None = _at("I", "", "AFE status")
    mcu_pin_in_status: int | None = _at("I", "", "MCU inputs")
    mcu_pin_out_status: int | None = _at("I", "", "MCU outputs")
    bms_alarm_state1: int | None = _at("I", "", "Alarms 1")
    bms_alarm_state2: int | None = _at("I", "", "Alarms 2")
    bms_protect_state1: int | None = _at("I", "", "Protections 1")
    bms_protect_state2: int | None = _at("I", "", "Protections 2")
    bms_fault_state: int | None = _at("I", "", "Faults")
    accu_chg_energy: int | None = _at(
        "I", "Wh", "Lifetime charge energy", confirmed=True
    )
    accu_dsg_energy: int | None = _at(
        "I", "Wh", "Lifetime discharge energy", confirmed=True
    )
    pack_sn: str | None = _at("16s", "", "Pack serial number", confirmed=True)
    water_in_flag: int | None = _at("B", "", "Water ingress")

    spans: Mapping[str, range] = field(default_factory=dict)
    tail: bytes = b""

    @property
    def tail_offset(self) -> int:
        return max((span.stop for span in self.spans.values()), default=0)


def layout_fields() -> Iterator[tuple[str, Layout]]:
    """Yield every field of the heartbeat in wire order with its layout"""
    for f in fields(BmsHeartbeat):
        if (layout := f.metadata.get(_LAYOUT)) is not None:
            yield f.name, layout


def is_bms_heartbeat(cmd_set: int, cmd_id: int) -> bool:
    return (cmd_set, cmd_id) == (BMS_CMD_SET, BMS_CMD_ID)


def decode_bms_heartbeat(payload: bytes) -> BmsHeartbeat:
    """
    Decode as many fields as `payload` holds, in wire order

    Decoding stops at the first field that does not fit, so a shorter heartbeat
    version leaves the later fields `None` and anything left over ends up in `tail`.
    """
    values: dict[str, Any] = {}
    spans: dict[str, range] = {}
    offset = 0

    for name, layout in layout_fields():
        fmt = (
            f"<{layout.fmt}"
            if layout.count is None
            else f"<{values[layout.count]}{layout.fmt}"
        )
        size = struct.calcsize(fmt)
        if offset + size > len(payload):
            break

        unpacked = struct.unpack_from(fmt, payload, offset)
        values[name] = _to_value(layout, unpacked)
        spans[name] = range(offset, offset + size)
        offset += size

    return BmsHeartbeat(**values, spans=spans, tail=payload[offset:])


def _to_value(layout: Layout, unpacked: tuple[Any, ...]) -> Any:
    if layout.count is not None:
        return unpacked
    if layout.fmt.endswith("s"):
        return unpacked[0].rstrip(b"\x00").decode("ascii", errors="replace")
    return unpacked[0]

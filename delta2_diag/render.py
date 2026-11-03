"""Terminal view of decoded packets"""

import struct
from collections import Counter
from collections.abc import Iterable
from typing import Any

from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .bms import (
    BmsHeartbeat,
    Layout,
    decode_bms_heartbeat,
    is_bms_heartbeat,
    layout_fields,
)
from .capture import CapturedPacket

_VERSIONS = frozenset({"sys_ver", "sys_loader_ver"})
_HEX = frozenset({"bms_heartbeat_ver", "ecloud_ocv", "balance_cmd"})
_BITS = frozenset(
    {
        "mos_state",
        "balance_state",
        "bms_fault",
        "bq_sys_stat_reg",
        "all_err_code",
        "all_bms_fault",
        "afe_sys_status",
        "mcu_pin_in_status",
        "mcu_pin_out_status",
        "bms_alarm_state1",
        "bms_alarm_state2",
        "bms_protect_state1",
        "bms_protect_state2",
        "bms_fault_state",
    }
)
_PERCENT = frozenset({"real_soh", "calendar_soh", "cycle_soh"})
_HEX_PREVIEW = 16

# The DELTA 2 sends these but leaves them unfilled or fills them with values that
# contradict the rest of the heartbeat, on both units captured so far. Comment a line
# out to show that field again.
_HIDDEN = frozenset(
    {
        "cell_temp",  # 0 °C on every sensor while the cells read 31-33 °C
        "hw_ver",  # "V0.0.1" on every unit, looks like a placeholder
        "ecloud_ocv",  # always 0xffff
        "bms_sn",  # all zeros
        "accu_chg_cap",  # discharged is 42-77 % of charged, impossible for LFP
        "accu_dsg_cap",  # see `accu_chg_cap`
        "real_soh",  # always 0
        "calendar_soh",  # always 0
        "cycle_soh",  # about 50000, not a percentage
    }
)

_KNOWN_PACKETS = {
    (0x02, 0x20, 0x02): "PD: ports and total power",
    (0x03, 0x20, 0x02): "EMS: charge management",
    (0x03, 0x03, 0x0E): "Extra batteries",
    (0x04, 0x20, 0x02): "Inverter",
    (0x05, 0x20, 0x02): "MPPT: solar input and 12 V",
    (0x35, 0x35, 0x20): "Ping",
}

_UNKNOWN_STYLE = "bold yellow"
_MIN_STYLE = "bold cyan"
_MAX_STYLE = "bold red"


def render_heartbeat(console: Console, packet: CapturedPacket) -> None:
    heartbeat = decode_bms_heartbeat(packet.payload)
    pack = "main" if heartbeat.num == 0 else "extra"
    console.print(
        Rule(
            f"BMS heartbeat of pack {heartbeat.num} ({pack}) · src 0x{packet.src:02x} · "
            f"{len(packet.payload)} bytes · {packet.time:%Y-%m-%d %H:%M:%S}"
        )
    )
    console.print(_summary(heartbeat))
    if heartbeat.cell_vol:
        console.print(_cells(heartbeat.cell_vol))
    console.print(_field_table(heartbeat, packet.payload))
    console.print(_hexdump(packet.payload, heartbeat.tail_offset))


def render_packet_stats(console: Console, packets: Iterable[CapturedPacket]) -> None:
    counts = Counter((p.src, p.cmd_set, p.cmd_id, len(p.payload)) for p in packets)
    table = Table(title="Received packets", title_justify="left")
    for column in ("src", "cmd_set", "cmd_id", "Bytes", "Count", "What it is"):
        table.add_column(column)
    for (src, cmd_set, cmd_id, size), count in sorted(counts.items()):
        table.add_row(
            f"0x{src:02x}",
            f"0x{cmd_set:02x}",
            f"0x{cmd_id:02x}",
            str(size),
            str(count),
            _describe_packet(src, cmd_set, cmd_id),
        )
    console.print(table)


def _describe_packet(src: int, cmd_set: int, cmd_id: int) -> str:
    if is_bms_heartbeat(cmd_set, cmd_id):
        return "BMS heartbeat"
    if (cmd_set, cmd_id) == (0x20, 0x58):
        return "Battery module info"
    return _KNOWN_PACKETS.get((src, cmd_set, cmd_id), "unknown")


def _summary(hb: BmsHeartbeat) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    rows = {
        "Design capacity": _ah(hb.design_cap),
        "Full capacity": _with_share(
            _ah(hb.full_cap), hb.full_cap, hb.design_cap, "of design"
        ),
        "Remaining capacity": _with_share(
            _ah(hb.remain_cap), hb.remain_cap, hb.full_cap, "of full"
        ),
        "Cycles": _opt(hb.cycles),
        "SOH": _soh(hb),
        "Charge": _charge(hb),
        "Voltage, current": _power(hb),
        "Cells": _cell_overview(hb),
        "Temperatures": _temperatures(hb),
        "Errors": _errors(hb),
        "Lifetime totals": _totals(hb),
        "Firmware": _firmware(hb),
        "Serial numbers": _serials(hb),
    }
    for label, value in rows.items():
        if value:
            table.add_row(label, value)
    return table


def _cells(cell_vol: tuple[int, ...]) -> Table:
    low, high = min(cell_vol), max(cell_vol)
    table = Table(
        title=(
            f"Cell voltages, mV (min {low} in cyan, max {high} in red, "
            f"average {sum(cell_vol) / len(cell_vol):.1f})"
        ),
        title_justify="left",
        show_header=False,
    )
    per_row = 8
    for _ in range(per_row):
        table.add_column(justify="right")
    cells = []
    for index, mv in enumerate(cell_vol, start=1):
        style = _MAX_STYLE if mv == high else _MIN_STYLE if mv == low else ""
        cells.append(Text(f"{index:>2}: {mv}", style=style))
    for start in range(0, len(cells), per_row):
        table.add_row(*cells[start : start + per_row])
    return table


def _field_table(hb: BmsHeartbeat, payload: bytes) -> Table:
    hidden = [name for name in hb.spans if name in _HIDDEN]
    table = Table(
        title="All fields (? means the field's position or meaning is not confirmed yet)",
        title_justify="left",
        caption=f"Hidden as unreliable: {', '.join(hidden)}" if hidden else None,
        caption_justify="left",
    )
    table.add_column("Offset", justify="right")
    table.add_column("Field")
    table.add_column("Description")
    table.add_column("Bytes (hex)")
    table.add_column("Value")
    table.add_column("")
    for name, layout in layout_fields():
        if (span := hb.spans.get(name)) is None or name in _HIDDEN:
            continue
        raw = payload[span.start : span.stop]
        preview = raw[:_HEX_PREVIEW].hex(" ") + (
            " …" if len(raw) > _HEX_PREVIEW else ""
        )
        table.add_row(
            str(span.start),
            name,
            layout.label,
            preview,
            _format_value(name, layout, getattr(hb, name)),
            "" if layout.confirmed else "?",
        )
    if hb.tail:
        table.add_row(
            str(hb.tail_offset),
            Text("(unknown)", style=_UNKNOWN_STYLE),
            "bytes after the known fields",
            hb.tail.hex(" "),
            f"{len(hb.tail)} bytes",
            "?",
        )
    return table


def _hexdump(payload: bytes, unknown_from: int) -> Table:
    caption = (
        f"{len(payload) - unknown_from} unrecognized bytes in yellow"
        if unknown_from < len(payload)
        else "all bytes recognized"
    )
    table = Table(
        title=f"Payload, hex ({caption})",
        title_justify="left",
        show_header=False,
        box=None,
    )
    table.add_column(justify="right", style="dim")
    table.add_column()
    table.add_column(style="dim")
    for start in range(0, len(payload), 16):
        row = Text()
        for offset in range(start, min(start + 16, len(payload))):
            style = _UNKNOWN_STYLE if offset >= unknown_from else ""
            row.append(f"{payload[offset]:02x} ", style=style)
        chunk = payload[start : start + 16]
        ascii_text = "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)
        table.add_row(str(start), row, ascii_text)
    return table


def _format_value(name: str, layout: Layout, value: Any) -> str:
    suffix = f" {layout.unit}" if layout.unit else ""
    if isinstance(value, tuple):
        return ", ".join(str(v) for v in value) + suffix
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, float):
        note = " (implausible)" if name in _PERCENT and not 0 <= value <= 100 else ""
        return f"{value:.2f}{suffix}{note}"

    width = struct.calcsize(f"<{layout.fmt}") * 2
    if layout.fmt.isupper() and value == (1 << (width * 4)) - 1:
        return f"0x{value:0{width}x} (no data)"
    if name in _VERSIONS:
        return f"{_version(value)} (0x{value:08x})"
    if name in _BITS:
        bits = f", bits {_bits(value)}" if value else ""
        return f"0x{value:0{width}x}{bits}"
    if name in _HEX:
        return f"0x{value:0{width}x}"
    return f"{value}{suffix}"


def _version(value: int) -> str:
    return ".".join(str(b) for b in value.to_bytes(4, "big"))


def _bits(value: int) -> str:
    return ", ".join(str(bit) for bit in range(value.bit_length()) if value >> bit & 1)


def _opt(value: object) -> str | None:
    return None if value is None else str(value)


def _shown(hb: BmsHeartbeat, name: str) -> Any:
    return None if name in _HIDDEN else getattr(hb, name)


def _ah(mah: int | None) -> str | None:
    return None if mah is None else f"{mah / 1000:.3f} Ah ({mah} mAh)"


def _with_share(
    text: str | None, part: int | None, whole: int | None, of_what: str
) -> str | None:
    if text is None or part is None or not whole:
        return text
    return f"{text}, {100 * part / whole:.1f} % {of_what}"


def _soh(hb: BmsHeartbeat) -> str | None:
    if hb.soh is None:
        return None
    parts = [f"{hb.soh} % (reported by BMS)"]
    for label, name in (
        ("actual", "real_soh"),
        ("calendar", "calendar_soh"),
        ("cycle", "cycle_soh"),
    ):
        if (value := _shown(hb, name)) is not None:
            note = "" if 0 <= value <= 100 else " (implausible)"
            parts.append(f"{label} {value:.2f}{note}")
    return "; ".join(parts)


def _charge(hb: BmsHeartbeat) -> str | None:
    if hb.f32_show_soc is None:
        return None
    text = f"{hb.f32_show_soc:.2f} % on screen"
    if hb.act_soc is not None:
        text += f", {hb.act_soc:.2f} % actual"
    return text


def _power(hb: BmsHeartbeat) -> str | None:
    if hb.vol is None or hb.amp is None:
        return None
    return f"{hb.vol / 1000:.3f} V, {hb.amp / 1000:+.3f} A"


def _cell_overview(hb: BmsHeartbeat) -> str | None:
    if hb.max_cell_vol is None or hb.min_cell_vol is None:
        return None
    text = (
        f"{hb.min_cell_vol / 1000:.3f} … {hb.max_cell_vol / 1000:.3f} V, "
        f"spread {hb.max_cell_vol - hb.min_cell_vol} mV"
    )
    if hb.cell_series_num is not None:
        text = f"{hb.cell_series_num} cells, {text}"
    return text


def _temperatures(hb: BmsHeartbeat) -> str | None:
    if hb.temp is None:
        return None
    parts = [
        f"pack {hb.temp} °C",
        f"cells {hb.min_cell_temp} … {hb.max_cell_temp} °C",
        f"MOSFET {hb.min_mos_temp} … {hb.max_mos_temp} °C",
    ]
    if (cell_temp := _shown(hb, "cell_temp")) is not None:
        parts.append(f"cell sensors: {', '.join(map(str, cell_temp))} °C")
    return "; ".join(parts)


def _errors(hb: BmsHeartbeat) -> str | None:
    if hb.err_code is None:
        return None
    parts = [f"code {hb.err_code}"]
    if hb.all_err_code:
        parts.append(f"all codes (bits): {_bits(hb.all_err_code)}")
    parts.append(f"BMS fault 0x{hb.bms_fault:02x}")
    parts.append(f"AFE protection 0x{hb.bq_sys_stat_reg:02x}")
    return "; ".join(parts)


def _totals(hb: BmsHeartbeat) -> str | None:
    parts = []
    if (charged := _shown(hb, "accu_chg_cap")) is not None:
        parts.append(f"charged {charged / 1000:.1f} Ah")
    if (discharged := _shown(hb, "accu_dsg_cap")) is not None:
        parts.append(f"discharged {discharged / 1000:.1f} Ah")
    if hb.accu_chg_energy is not None and hb.accu_dsg_energy is not None:
        parts.append(f"energy {hb.accu_chg_energy} / {hb.accu_dsg_energy} Wh")
    return ", ".join(parts) or None


def _firmware(hb: BmsHeartbeat) -> str | None:
    if hb.sys_ver is None:
        return None
    parts = [f"BMS {_version(hb.sys_ver)}"]
    if hb.sys_loader_ver is not None:
        parts.append(f"bootloader {_version(hb.sys_loader_ver)}")
    if hw_ver := _shown(hb, "hw_ver"):
        parts.append(f"board {hw_ver}")
    if hb.bms_heartbeat_ver is not None:
        parts.append(f"packet format 0x{hb.bms_heartbeat_ver:04x}")
    return ", ".join(parts)


def _serials(hb: BmsHeartbeat) -> str | None:
    serials = [
        sn
        for name in ("bms_sn", "pack_sn")
        if (sn := _shown(hb, name)) and sn.strip("0")
    ]
    return ", ".join(serials) or None

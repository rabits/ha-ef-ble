"""
Command line entry point: `python -m delta2_diag <command>`

`login` stores the EcoFlow user ID that BLE authentication needs, `scan` lists EcoFlow
devices nearby, `dump` connects, records every packet for a while and shows the
decoded BMS heartbeat, and `decode` shows the same for a saved capture.
"""

import argparse
import asyncio
import getpass
import logging
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from custom_components.ef_ble.eflib.login import Region

from .account import AccountError, fetch_user_id, load_user_id, save_user_id
from .bms import is_bms_heartbeat
from .capture import CapturedPacket, CaptureWriter, read_capture
from .render import render_heartbeat, render_packet_stats
from .station import (
    StationError,
    StationSession,
    find_station,
    mask_address,
    mask_serial,
    scan,
)

_console = Console(highlight=False)


async def _login(args: argparse.Namespace) -> None:
    email = input("EcoFlow account email: ").strip()  # noqa: ASYNC250 - loop is idle
    password = getpass.getpass("Password (not shown): ")
    user_id = await fetch_user_id(email, password, Region(args.region))
    path = save_user_id(user_id)
    _console.print(f"User ID saved to {path}")


async def _scan(args: argparse.Namespace) -> None:
    _console.print(f"Scanning for EcoFlow devices for {args.timeout:.0f} s…")
    stations = await scan(args.timeout)
    if not stations:
        _console.print("No EcoFlow devices found.")
        return

    table = Table()
    for column in ("Model", "Serial number", "Address", "RSSI", "DELTA 2?"):
        table.add_column(column)
    for station in stations:
        table.add_row(
            station.model,
            mask_serial(station.serial),
            mask_address(station.ble_device.address),
            str(station.advertisement.rssi),
            "yes" if station.is_delta2_family else "",
        )
    _console.print(table)


async def _dump(args: argparse.Namespace) -> None:
    if (user_id := load_user_id()) is None:
        raise AccountError("no User ID: run `login` first")

    _console.print("Looking for the station…")
    station = await find_station(args.scan_timeout, args.sn_suffix)
    _console.print(f"Found {station.model} {mask_serial(station.serial)}, connecting…")

    path = args.captures / f"{datetime.now():%Y%m%d-%H%M%S}-dump.jsonl"
    packets: list[CapturedPacket] = []
    with CaptureWriter(path) as writer:

        def on_packet(packet: CapturedPacket) -> None:
            writer.write(packet)
            packets.append(packet)

        async with StationSession(station, user_id, on_packet) as session:
            _console.print(
                f"Authenticated. Listening for {args.listen:.0f} s, "
                "sending nothing to the station…"
            )
            await asyncio.sleep(args.listen)
            connected = session.is_connected

    _show_heartbeats(_first_per_pack(packets))
    render_packet_stats(_console, packets)
    _console.print(
        f"Sent to the station: {session.sent_before_auth} packets during "
        f"authentication, {session.sent_after_auth} after it."
    )
    if not connected:
        _console.print(
            "[yellow]The station dropped the connection before listening ended."
        )
    _console.print(f"Raw packets saved to {path}")


async def _decode(args: argparse.Namespace) -> None:
    packets = list(read_capture(args.capture))
    heartbeats = _distinct_heartbeats(packets) if args.all else _last_per_pack(packets)
    _show_heartbeats(heartbeats)
    render_packet_stats(_console, packets)


def _show_heartbeats(heartbeats: list[CapturedPacket]) -> None:
    if not heartbeats:
        _console.print("[yellow]No BMS heartbeat received.")
    for packet in heartbeats:
        render_heartbeat(_console, packet)


def _heartbeats(packets: list[CapturedPacket]) -> list[CapturedPacket]:
    return [
        p
        for p in packets
        if p.valid and p.payload and is_bms_heartbeat(p.cmd_set, p.cmd_id)
    ]


def _first_per_pack(packets: list[CapturedPacket]) -> list[CapturedPacket]:
    first: dict[int, CapturedPacket] = {}
    for packet in _heartbeats(packets):
        first.setdefault(packet.payload[0], packet)
    return [first[num] for num in sorted(first)]


def _last_per_pack(packets: list[CapturedPacket]) -> list[CapturedPacket]:
    last = {packet.payload[0]: packet for packet in _heartbeats(packets)}
    return [last[num] for num in sorted(last)]


def _distinct_heartbeats(packets: list[CapturedPacket]) -> list[CapturedPacket]:
    seen: set[bytes] = set()
    distinct = []
    for packet in _heartbeats(packets):
        if packet.payload not in seen:
            seen.add(packet.payload)
            distinct.append(packet)
    return distinct


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m delta2_diag",
        description="EcoFlow DELTA 2 service data over Bluetooth (read-only)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="more detailed log: -v for INFO, -vv for DEBUG",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login", help="fetch and store the EcoFlow User ID")
    login.add_argument(
        "--region",
        choices=[region.value for region in Region],
        default=Region.AUTO.value,
        help="EcoFlow server to log in to (detected automatically by default)",
    )
    login.set_defaults(handler=_login)

    scan_cmd = commands.add_parser("scan", help="list EcoFlow devices nearby")
    scan_cmd.add_argument("--timeout", type=float, default=10, help="seconds to scan")
    scan_cmd.set_defaults(handler=_scan)

    dump = commands.add_parser(
        "dump", help="connect, record packets and show the BMS heartbeat"
    )
    dump.add_argument(
        "--sn-suffix", help="last characters of the serial number, if there are several"
    )
    dump.add_argument(
        "--listen", type=float, default=15, help="seconds to listen (default 15)"
    )
    dump.add_argument("--scan-timeout", type=float, default=20, help="seconds to scan")
    dump.add_argument(
        "--captures",
        type=Path,
        default=Path("captures"),
        help="directory for raw packet files (default ./captures)",
    )
    dump.set_defaults(handler=_dump)

    decode = commands.add_parser("decode", help="decode a saved packet file")
    decode.add_argument("capture", type=Path, help=".jsonl file from the dump command")
    decode.add_argument(
        "--all",
        action="store_true",
        help="show every distinct BMS heartbeat, not only the last one",
    )
    decode.set_defaults(handler=_decode)
    return parser


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(
        level=(logging.ERROR, logging.INFO, logging.DEBUG)[min(args.verbose, 2)],
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(args.handler(args))
    except (AccountError, StationError) as e:
        _console.print(f"[red]Error:[/red] {escape(str(e))}")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()

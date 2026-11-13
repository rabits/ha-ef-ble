"""
Answer the ATT MTU request the kernel drops when a controller reports a link late

Some controllers, the Realtek RTL8852BU for one, deliver the first ACL packet of an LE
link before the event that reports the link, so the kernel drops it as data for an
unknown handle. The DELTA Pro opens each link with an MTU request and sends no
notification until that request is answered, so we answer it from the HCI monitor.
"""

import asyncio
import contextlib
import ctypes
import functools
import logging
import os
import socket
import struct
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

_AF_BLUETOOTH = 31
_BTPROTO_HCI = 1
_HCI_DEV_NONE = 0xFFFF
_HCI_CHANNEL_RAW = 0
_HCI_CHANNEL_MONITOR = 2

_MONITOR_EVENT = 3
_MONITOR_ACL_RX = 5
_MONITOR_FRAME_MAX = 4096

_HCI_ACL_PACKET = 0x02
_EVT_DISCONNECTION_COMPLETE = 0x05
_EVT_LE_META = 0x3E
_LE_CONNECTION_COMPLETE = 0x01
_LE_ENHANCED_CONNECTION_COMPLETE = 0x0A

_ATT_CID = 0x0004
_ATT_EXCHANGE_MTU_REQ = 0x02
_ATT_EXCHANGE_MTU_RSP = 0x03
# The MTU BlueZ offers in its own request, so both exchanges agree
_SERVER_MTU = 517


@dataclass(frozen=True)
class MtuAnswer:
    """HCI packet that answers a dropped MTU request, and the adapter to write it to"""

    adapter: int
    packet: bytes


class EarlyMtuWatcher:
    """
    Find the ATT MTU request of one device that the kernel dropped, in HCI monitor frames

    The kernel copies each frame to the monitor before it handles it, so a request seen
    before the event that reports its link is one the kernel had no link for.
    """

    def __init__(self, address: str) -> None:
        # HCI carries addresses little endian
        self._peer = bytes.fromhex(address.replace(":", ""))[::-1]
        self._early_requests: set[tuple[int, int]] = set()

    def feed(self, frame: bytes) -> MtuAnswer | None:
        """Return the answer one monitor frame calls for, if any"""
        if len(frame) < 6:
            return None
        opcode, adapter, length = struct.unpack_from("<HHH", frame)
        body = frame[6 : 6 + length]
        if opcode == _MONITOR_ACL_RX:
            self._on_acl(adapter, body)
        elif opcode == _MONITOR_EVENT:
            return self._on_event(adapter, body)
        return None

    def _on_acl(self, adapter: int, body: bytes) -> None:
        if (
            len(body) >= 9
            and struct.unpack_from("<H", body, 6)[0] == _ATT_CID
            and body[8] == _ATT_EXCHANGE_MTU_REQ
        ):
            handle = struct.unpack_from("<H", body)[0] & 0x0FFF
            self._early_requests.add((adapter, handle))

    def _on_event(self, adapter: int, body: bytes) -> MtuAnswer | None:
        code = body[0] if body else None
        if code == _EVT_DISCONNECTION_COMPLETE and len(body) >= 5 and body[2] == 0:
            # A link that was up before we started may close and hand its handle over
            handle = struct.unpack_from("<H", body, 3)[0] & 0x0FFF
            self._early_requests.discard((adapter, handle))
            return None
        if (
            code != _EVT_LE_META
            or len(body) < 14
            or body[2]
            not in (_LE_CONNECTION_COMPLETE, _LE_ENHANCED_CONNECTION_COMPLETE)
        ):
            return None

        handle = struct.unpack_from("<H", body, 4)[0] & 0x0FFF
        if (adapter, handle) not in self._early_requests:
            return None
        self._early_requests.discard((adapter, handle))
        if body[3] != 0 or body[8:14] != self._peer:
            return None

        att = struct.pack("<BH", _ATT_EXCHANGE_MTU_RSP, _SERVER_MTU)
        l2cap = struct.pack("<HH", len(att), _ATT_CID) + att
        # Packet boundary flag 0b00, as the kernel sends LE data: the DELTA Pro ignored
        # an answer sent with 0b10
        acl = struct.pack("<HH", handle, len(l2cap)) + l2cap
        return MtuAnswer(adapter, bytes([_HCI_ACL_PACKET]) + acl)


class _SockaddrHci(ctypes.Structure):
    _fields_ = [
        ("family", ctypes.c_ushort),
        ("dev", ctypes.c_ushort),
        ("channel", ctypes.c_ushort),
    ]


@functools.cache
def _libc() -> ctypes.CDLL:
    return ctypes.CDLL(None, use_errno=True)


def _hci_socket(dev: int, channel: int) -> socket.socket:
    # `socket.bind((dev, channel))` fails with EBADFD for the monitor on Python 3.14
    libc = _libc()
    sock = socket.socket(_AF_BLUETOOTH, socket.SOCK_RAW, _BTPROTO_HCI)
    addr = _SockaddrHci(_AF_BLUETOOTH, dev, channel)
    if libc.bind(sock.fileno(), ctypes.byref(addr), ctypes.sizeof(addr)) != 0:
        errno = ctypes.get_errno()
        sock.close()
        raise OSError(errno, os.strerror(errno))
    sock.setblocking(False)
    return sock


class _MonitorResponder:
    """Read the HCI monitor without blocking and send the answers the watcher finds"""

    def __init__(
        self, monitor: socket.socket, address: str, logger: logging.Logger
    ) -> None:
        self._monitor = monitor
        self._watcher = EarlyMtuWatcher(address)
        self._logger = logger
        self._loop = asyncio.get_running_loop()

    def start(self) -> None:
        self._loop.add_reader(self._monitor.fileno(), self._read)

    def stop(self) -> None:
        self._loop.remove_reader(self._monitor.fileno())

    def _read(self) -> None:
        while True:
            try:
                frame = self._monitor.recv(_MONITOR_FRAME_MAX)
            except BlockingIOError:
                return
            except OSError as e:
                self._logger.debug("Reading the HCI monitor failed: %s", e)
                self.stop()
                return
            if (answer := self._watcher.feed(frame)) is not None:
                self._send(answer)

    def _send(self, answer: MtuAnswer) -> None:
        # Bound only for the send: the kernel copies all adapter traffic to a raw socket
        try:
            with _hci_socket(answer.adapter, _HCI_CHANNEL_RAW) as raw:
                raw.send(answer.packet)
        except OSError as e:
            self._logger.debug("Could not answer the dropped ATT MTU request: %s", e)
            return
        self._logger.info(
            "Answered the ATT MTU request the kernel dropped on hci%d", answer.adapter
        )


@contextlib.asynccontextmanager
async def answer_early_mtu_request(
    address: str, logger: logging.Logger
) -> AsyncIterator[None]:
    """
    Answer the MTU request of `address` if the kernel drops it during the connect

    Does nothing where the HCI monitor cannot be opened (not Linux, no CAP_NET_RAW) and
    finds nothing to answer when the link goes through an ESPHome proxy.
    """
    if sys.platform != "linux":
        yield
        return

    try:
        monitor = _hci_socket(_HCI_DEV_NONE, _HCI_CHANNEL_MONITOR)
    except OSError as e:
        logger.debug(
            "HCI monitor unavailable, early MTU requests stay unanswered: %s", e
        )
        yield
        return

    with monitor:
        responder = _MonitorResponder(monitor, address, logger)
        responder.start()
        try:
            yield
        finally:
            responder.stop()

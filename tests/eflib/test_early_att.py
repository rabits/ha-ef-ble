import struct

import pytest

from custom_components.ef_ble.eflib.early_att import EarlyMtuWatcher

ADDRESS = "AA:BB:CC:DD:EE:FF"
ADAPTER = 1
HANDLE = 0x0123


def _monitor_frame(opcode: int, body: bytes) -> bytes:
    return struct.pack("<HHH", opcode, ADAPTER, len(body)) + body


def _mtu_request() -> bytes:
    att = struct.pack("<BH", 0x02, 247)
    l2cap = struct.pack("<HH", len(att), 0x0004) + att
    # Packet boundary flag 0b10, as a controller marks the start of a frame
    return _monitor_frame(5, struct.pack("<HH", HANDLE | 0x2000, len(l2cap)) + l2cap)


def _connection_complete(address: str = ADDRESS, subevent: int = 0x0A) -> bytes:
    peer = bytes.fromhex(address.replace(":", ""))[::-1]
    params = bytes([subevent, 0x00]) + struct.pack("<H", HANDLE) + b"\x00\x01" + peer
    params += bytes(19 if subevent == 0x0A else 7)
    return _monitor_frame(3, bytes([0x3E, len(params)]) + params)


def _disconnection_complete() -> bytes:
    params = b"\x00" + struct.pack("<H", HANDLE) + b"\x13"
    return _monitor_frame(3, bytes([0x05, len(params)]) + params)


@pytest.mark.parametrize("subevent", [0x01, 0x0A], ids=["legacy", "enhanced"])
def test_mtu_request_before_connection_complete_is_answered(subevent: int) -> None:
    watcher = EarlyMtuWatcher(ADDRESS)
    assert watcher.feed(_mtu_request()) is None

    answer = watcher.feed(_connection_complete(subevent=subevent))

    assert answer is not None
    assert answer.adapter == ADAPTER
    packet_type, handle_flags, _, _, cid, opcode = struct.unpack_from(
        "<BHHHHB", answer.packet
    )
    assert packet_type == 0x02
    assert handle_flags == HANDLE  # packet boundary flag 0b00
    assert cid == 0x0004
    assert opcode == 0x03


@pytest.mark.parametrize(
    "frames",
    [
        pytest.param(
            [_connection_complete(), _mtu_request()],
            id="kernel_saw_the_link",
        ),
        pytest.param(
            [_mtu_request(), _connection_complete("11:22:33:44:55:66")],
            id="another_device",
        ),
        pytest.param(
            [
                _mtu_request(),
                _disconnection_complete(),
                _connection_complete(),
                _mtu_request(),
            ],
            id="handle_of_a_closed_link_reused",
        ),
    ],
)
def test_other_mtu_requests_are_not_answered(frames: list[bytes]) -> None:
    watcher = EarlyMtuWatcher(ADDRESS)

    assert [watcher.feed(frame) for frame in frames] == [None] * len(frames)

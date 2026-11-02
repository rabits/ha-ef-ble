"""Raw packet capture, one JSON object per line"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self


@dataclass(frozen=True)
class CapturedPacket:
    """
    One frame as it came off the link, after BLE decryption

    `frame` is the whole packet with header and CRC, its payload still XORed the way
    the station sends it; `payload` is what the device class parsed out of it.
    """

    time: datetime
    src: int
    dst: int
    cmd_set: int
    cmd_id: int
    payload: bytes
    frame: bytes
    valid: bool = True

    def to_json(self) -> str:
        return json.dumps(
            {
                "time": self.time.isoformat(timespec="milliseconds"),
                "src": self.src,
                "dst": self.dst,
                "cmd_set": self.cmd_set,
                "cmd_id": self.cmd_id,
                "payload": self.payload.hex(),
                "frame": self.frame.hex(),
                "valid": self.valid,
            }
        )

    @classmethod
    def from_json(cls, line: str) -> Self:
        data = json.loads(line)
        return cls(
            time=datetime.fromisoformat(data["time"]),
            src=data["src"],
            dst=data["dst"],
            cmd_set=data["cmd_set"],
            cmd_id=data["cmd_id"],
            payload=bytes.fromhex(data["payload"]),
            frame=bytes.fromhex(data["frame"]),
            valid=data["valid"],
        )


class CaptureWriter:
    """Append packets to a capture file, flushing each one so a crash loses nothing"""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._file = path.open("a", encoding="utf-8")

    def write(self, packet: CapturedPacket) -> None:
        self._file.write(packet.to_json() + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def read_capture(path: Path) -> Iterator[CapturedPacket]:
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                yield CapturedPacket.from_json(line)

from datetime import UTC, datetime

from delta2_diag.capture import CapturedPacket, CaptureWriter, read_capture


def test_capture_file_reads_back_what_was_written(tmp_path):
    packet = CapturedPacket(
        time=datetime(2026, 11, 2, 21, 30, 0, 123000, tzinfo=UTC),
        src=0x03,
        dst=0x21,
        cmd_set=0x20,
        cmd_id=0x32,
        payload=bytes.fromhex("0001020304"),
        frame=bytes.fromhex("aa02050000"),
        valid=False,
    )
    path = tmp_path / "nested" / "capture.jsonl"

    with CaptureWriter(path) as writer:
        writer.write(packet)

    assert list(read_capture(path)) == [packet]

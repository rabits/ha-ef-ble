"""
Full BMS heartbeat decoding against real captures

`_DELTA2_FRAME` is a decrypted frame from a DELTA 2 debug log published in
rabits/ha-ef-ble issue #116 (payload still XORed, as it comes off the link). The other
payloads are taken from the DELTA 3 1500 and DELTA 2 Max sequences in `tests/eflib`;
the two serial numbers in the extra battery payload are replaced with placeholders.
"""

import pytest

from custom_components.ef_ble.eflib.packet import Packet
from delta2_diag.bms import decode_bms_heartbeat

_DELTA2_FRAME = bytes.fromhex(
    "aa02bc00062f880422ab11840321203288898a9f888888fa8a838add57478888d17777779289a8c6"
    "8888d4cc8888a8c68888af888888ec76847384929293938888a8c68888264b22ca88888888888888"
    "88888888888a88888b88987484738475847684758475847584738474847584758475847584758475"
    "8473848b888888888888deb8a6b8a6b98b897777b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8d88a8888"
    "24ca88340eb7994c22ca8988838a8a8888880888888888887c658388e3708c888888888888888888"
    "88b5cfcf63ef"
)

_DELTA3_1500_MAIN = bytes.fromhex(
    "00010200000000250000026226d0000091ffffff2001307500006c73000030750000010000006406"
    "0d030d1f1e222200003075000068ccc442000000000000000000000000030000030010050d040d03"
    "0d050d050d040d040d040d040d030d050d050d050d030d060d050d041f001e001e001e0056302e31"
    "2e310301ffff303030303030303030303030303030304e020000c44200000000b6d9c44204000002"
    "02000000000000000000acbd0000e5570000000000000000000000f74747"
)

_DELTA3_EXTRA_BATTERY = bytes.fromhex(
    "0101020000000041000002640ed00000020000002000204e00001f4e0000204e0000010000006403"
    "0d000d201e1e1e0003d0070000baffc74200000000000000009f0f0000000000030010000d000d00"
    "0d010d000d000d010d010d010d010d020d000d030d020d010d010d041e001e0020001e0056312e30"
    "2e310601ffff503336313030303030303030303030304f07d92bc8425055553f4c2cc842ffffffff"
    "03000000000000000000096a0000a83100000000c842000000000000c842021e001e000120000001"
    "1f0020002000000000001f001f000000000000000000000000000000000000000000000000000000"
    "000000000000000000000300000027c1000017200100000000000000000000000000000000000000"
    "0000d3050000980200005033363130303030303030303030303000"
)

_DELTA2_MAX_MAIN = bytes.fromhex(
    "00010200000000330101024b26d0000087ffffff1001409c0000bf73000070990000040000006406"
    "0d040d1210190f0000409c000016df9642000000000000000000000000030000020010050d040d04"
    "0d040d050d050d040d040d050d050d050d050d060d050d050d050d05100011001200100010005630"
    "2e312e320301ffff30303030303030303030303030303030510200009642000000004ebc93420600"
    "010202000000000000000000ffffffffffffffff00000000000000000000c642"
)

_DELTA2_PAYLOAD = Packet.from_bytes(_DELTA2_FRAME, xor_payload=True).payload

_MAIN_PACKS = pytest.mark.parametrize(
    ("payload", "cell_temp", "hw_ver"),
    [
        pytest.param(_DELTA2_PAYLOAD, (0, 0, 0), "V0.0.1", id="delta2"),
        pytest.param(_DELTA3_1500_MAIN, (31, 30, 30, 30), "V0.1.1", id="delta3_1500"),
        pytest.param(_DELTA2_MAX_MAIN, (16, 17, 18, 16, 16), "V0.1.2", id="delta2_max"),
    ],
)


@_MAIN_PACKS
def test_cell_voltages_agree_with_reported_extremes(payload, cell_temp, hw_ver):
    heartbeat = decode_bms_heartbeat(payload)

    assert heartbeat.cell_series_num == 16
    assert heartbeat.cell_vol is not None
    assert len(heartbeat.cell_vol) == 16
    assert max(heartbeat.cell_vol) == heartbeat.max_cell_vol
    assert min(heartbeat.cell_vol) == heartbeat.min_cell_vol
    assert heartbeat.max_vol_diff == heartbeat.max_cell_vol - heartbeat.min_cell_vol


@_MAIN_PACKS
def test_sensor_count_moves_the_fields_after_it(payload, cell_temp, hw_ver):
    heartbeat = decode_bms_heartbeat(payload)

    assert heartbeat.cell_temp == cell_temp
    assert heartbeat.hw_ver == hw_ver
    assert heartbeat.tail == b""


def test_delta2_capacity_and_wear_fields():
    heartbeat = decode_bms_heartbeat(_DELTA2_PAYLOAD)

    assert heartbeat.design_cap == 20000
    assert heartbeat.full_cap == 20000
    assert heartbeat.remain_cap == 17500
    assert heartbeat.cycles == 39
    assert heartbeat.soh == 100
    assert heartbeat.accu_chg_cap == 781812
    assert heartbeat.accu_dsg_cap == 325739


def test_error_bitmask_carries_the_current_error_code():
    heartbeat = decode_bms_heartbeat(_DELTA2_PAYLOAD)

    assert heartbeat.err_code == 23
    assert heartbeat.all_err_code == 1 << heartbeat.err_code


def test_current_is_signed():
    assert decode_bms_heartbeat(_DELTA2_PAYLOAD).amp == -167


def test_extended_heartbeat_decodes_to_the_last_byte():
    heartbeat = decode_bms_heartbeat(_DELTA3_EXTRA_BATTERY)

    assert heartbeat.bms_heartbeat_ver == 0x0106
    assert heartbeat.mos_temp == (30, 30)
    assert heartbeat.env_temp == (32,)
    assert (heartbeat.max_env_temp, heartbeat.min_env_temp) == (32, 32)
    assert heartbeat.cur_sensor_temp == (31,)
    assert (heartbeat.accu_chg_energy, heartbeat.accu_dsg_energy) == (1491, 664)
    assert heartbeat.pack_sn == "P361000000000000"
    assert heartbeat.water_in_flag == 0
    assert heartbeat.tail == b""


def test_truncated_payload_keeps_the_partial_field_as_tail():
    heartbeat = decode_bms_heartbeat(_DELTA2_PAYLOAD[:80])

    assert heartbeat.cell_series_num == 16
    assert heartbeat.cell_vol is None
    assert heartbeat.tail == _DELTA2_PAYLOAD[75:80]
    assert heartbeat.tail_offset == 75

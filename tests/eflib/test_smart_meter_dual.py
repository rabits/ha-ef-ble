import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.smart_meter_dual import Device
from custom_components.ef_ble.eflib.packet import Packet


@pytest.fixture
def packets():
    return [
        # idle: CT1 (main feed) and CT2 both exporting a little solar
        (
            "aa13ef00fc2c2b5f000001a502210101fe1583232b9923266e5e59445b4e046744454f444593232a"
            "b60b9cb63fe9fe0e2b2b9be9fe0d2b2b2b2bf30d2ab10c2be9062be3062bcb062bc3062bfb042af3"
            "042bcb042bb61bf23ad9698e1b9cb63fe9811b32262b2b8f69362b2b33e90e2b2bf1691e2b2ba969"
            "162b2b1b69ae1adac9d895ce10d3445968c610a311d969de102b2b2b2bd6102b2b2b2bbe172b2b2b"
            "2bb6172b2b2b2beb162be6162e5b5968fe166912d969f6161839d969ce16f9c8e195c6162b2b2b2b"
            "de162b2b2b2bd616104ebce9ae152b2b2b2ba6152b2b2b2bbb152ab3152b8b152b811524262b2b3f"
            "69362b2b13690e2b2b2e689e15104ebce90414"
        ),
        # +400 W discharge from a battery on the CT1 circuit only
        (
            "aa13ef00fc2c9961000001a502210101fe153191992b9194dcecebf6e9fcb6d5f6f7fdf6f7219198"
            "04b94a4bef5a4cbc99992b5b4cbf9999999941bf9803be995bb49951b49979b49971b49949b69841"
            "b69979b69904a96c2a6bdb3ca94a4bef5a33a9809499993ddb849999b15bbc999943dbac999913db"
            "a49999b9db1ca839759a597ca2f98beada74a28f436bdb6ca29999999964a2999999990ca5999999"
            "9904a59999999959a49954a4828beada4ca4ca436bdb44a4022b6bdb7ca437af672774a499999999"
            "6ca49999999964a4a7884a5b1ca79999999914a79999999909a79801a79939a79933a7969499998d"
            "db849999a1dbbc999993da2ca7a7884a5b7354"
        ),
    ]


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "ES81XXXXXXXXX001")
    device._conn = mocker.AsyncMock()
    return device


def test_smart_meter_dual_claims_its_sn_prefix():
    assert Device.check(b"ES81ZXXXXXXXX001")
    assert not Device.check(b"BK21ZXXXXXXXX001")


async def test_smart_meter_dual_processes_display_upload(device, packets):
    for i, hex_packet in enumerate(packets):
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        assert not Packet.is_invalid(packet), f"Packet {i} parsed as InvalidPacket"
        assert (packet.src, packet.cmd_set, packet.cmd_id) == (0x02, 0xFE, 0x15)
        assert await device.data_parse(packet) is True


async def test_smart_meter_dual_reads_both_channels(device, packets):
    packet = await device.packet_parse(bytes.fromhex(packets[0]))
    await device.data_parse(packet)
    assert device.grid_power == pytest.approx(-37.2, abs=0.1)
    assert device.pv_power_sum == pytest.approx(-75.7, abs=0.1)
    assert device.l1_voltage == pytest.approx(242.4, abs=0.1)


async def test_smart_meter_dual_channel2_ignores_channel1_step(device, packets):
    """A load step on the CT1 circuit moves CT1 only"""
    readings = []
    for hex_packet in packets:
        packet = await device.packet_parse(bytes.fromhex(hex_packet))
        await device.data_parse(packet)
        readings.append((device.grid_power, device.pv_power_sum))
    (ct1_idle, ct2_idle), (ct1_step, ct2_step) = readings
    assert ct1_step - ct1_idle < -150
    assert abs(ct2_step - ct2_idle) < 50

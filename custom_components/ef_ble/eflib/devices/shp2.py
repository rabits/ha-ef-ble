import logging
from collections.abc import Sequence
from dataclasses import dataclass

from ..commands import TimeCommands
from ..devicebase import AdvertisementData, BLEDevice, DeviceBase
from ..packet import Packet
from ..pb import pd303_pb2_v5 as pd303_pb2
from ..props import (
    Field,
    ProtobufProps,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)

_LOGGER = logging.getLogger(__name__)

pb_time = proto_attr_mapper(pd303_pb2.ProtoTime)
pb_push_set = proto_attr_mapper(pd303_pb2.ProtoPushAndSet)


@dataclass
class CircuitPowerField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_watt)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return value[self.idx] if value and len(value) > self.idx else None


@dataclass
class CircuitCurrentField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_curr)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 4) if value and len(value) > self.idx else None


@dataclass
class ChannelPowerField(repeated_pb_field_type(list_field=pb_time.watt_info.ch_watt)):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 2) if value and len(value) > self.idx else None


def _errors(error_codes: pd303_pb2.ErrCode):
    return [e for e in error_codes.err_code if e != b"\x00\x00\x00\x00\x00\x00\x00\x00"]


class Device(DeviceBase, ProtobufProps):
    """Smart Home Panel 2"""

    SN_PREFIX = b"HD31"
    NAME_PREFIX = "EF-HD3"

    NUM_OF_CIRCUITS = 12
    NUM_OF_CHANNELS = 3

    battery_level = pb_field(pb_push_set.backup_incre_info.backup_bat_per)

    circuit_power_1 = CircuitPowerField(0)
    circuit_power_2 = CircuitPowerField(1)
    circuit_power_3 = CircuitPowerField(2)
    circuit_power_4 = CircuitPowerField(3)
    circuit_power_5 = CircuitPowerField(4)
    circuit_power_6 = CircuitPowerField(5)
    circuit_power_7 = CircuitPowerField(6)
    circuit_power_8 = CircuitPowerField(7)
    circuit_power_9 = CircuitPowerField(8)
    circuit_power_10 = CircuitPowerField(9)
    circuit_power_11 = CircuitPowerField(10)
    circuit_power_12 = CircuitPowerField(11)

    circuit_current_1 = CircuitCurrentField(0)
    circuit_current_2 = CircuitCurrentField(1)
    circuit_current_3 = CircuitCurrentField(2)
    circuit_current_4 = CircuitCurrentField(3)
    circuit_current_5 = CircuitCurrentField(4)
    circuit_current_6 = CircuitCurrentField(5)
    circuit_current_7 = CircuitCurrentField(6)
    circuit_current_8 = CircuitCurrentField(7)
    circuit_current_9 = CircuitCurrentField(8)
    circuit_current_10 = CircuitCurrentField(9)
    circuit_current_11 = CircuitCurrentField(10)
    circuit_current_12 = CircuitCurrentField(11)

    channel_power_1 = ChannelPowerField(0)
    channel_power_2 = ChannelPowerField(1)
    channel_power_3 = ChannelPowerField(2)

    in_use_power = pb_field(pb_time.watt_info.all_hall_watt)
    grid_power = pb_field(pb_time.watt_info.grid_watt)

    errors = pb_field(pb_push_set.backup_incre_info.errcode, _errors)
    error_count = Field[int]()
    error_happened = Field[bool]()

    @staticmethod
    def check(sn):
        return sn.startswith(Device.SN_PREFIX)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

    async def data_parse(self, packet: Packet) -> bool:
        """Processing the incoming notifications from the device"""
        processed = False
        self.reset_updated()

        prev_error_count = self.error_count

        if packet.src == 0x0B and packet.cmdSet == 0x0C:
            if (
                packet.cmdId == 0x01
            ):  # master_info, load_info, backup_info, watt_info, master_ver_info
                _LOGGER.debug(
                    "%s: %s: Parsed data: %r", self.address, self.name, packet
                )

                await self._conn.replyPacket(packet)

                self.update_from_bytes(pd303_pb2.ProtoTime, packet.payload)

                processed = True
            elif packet.cmdId == 0x20:  # backup_incre_info
                _LOGGER.debug(
                    "%s: %s: Parsed data: %r", self.address, self.name, packet
                )

                await self._conn.replyPacket(packet)
                self.update_from_bytes(pd303_pb2.ProtoPushAndSet, packet.payload)

                # TODO: Energy2_info.pv_height_charge_watts
                # TODO: Energy2_info.pv_low_charge_watts

                processed = True

            elif packet.cmdId == 0x21:  # is_get_cfg_flag
                _LOGGER.debug(
                    "%s: %s: Parsed data: %r", self.address, self.name, packet
                )
                self.update_from_bytes(pd303_pb2.ProtoPushAndSet, packet.payload)
                processed = True

        elif packet.src == 0x35 and packet.cmdSet == 0x35 and packet.cmdId == 0x20:
            _LOGGER.debug("%s: %s: Ping received: %r", self.address, self.name, packet)
            processed = True

        elif (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            # Device requested for time and timezone offset, so responding with that
            # otherwise it will not be able to send us predictions and config data
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        elif packet.src == 0x0B and packet.cmdSet == 0x01 and packet.cmdId == 0x55:
            # Device reply that it's online and ready
            self._conn._add_task(self.set_config_flag(True))
            processed = True

        self.error_count = len(self.errors) if self.errors is not None else None

        if (
            self.error_count is not None
            and prev_error_count is not None
            and self.error_count > prev_error_count
        ) or (self.error_count is not None and prev_error_count is None):
            self.error_happened = True
            _LOGGER.warning(
                "%s: %s: Error happened on device: %s",
                self.address,
                self.name,
                self.errors,
            )

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def set_config_flag(self, enable):
        """Send command to enable/disable sending config data from device to the host"""
        _LOGGER.debug("%s: setConfigFlag: %s", self._address, enable)

        ppas = pd303_pb2.ProtoPushAndSet()
        ppas.is_get_cfg_flag = enable
        payload = ppas.SerializeToString()
        packet = Packet(0x21, 0x0B, 0x0C, 0x21, payload, 0x01, 0x01, 0x13)

        await self._conn.sendPacket(packet)

    async def set_circuit_power(self, circuit_id, enable):
        """Send command to power on / off the specific circuit of the panel"""
        _LOGGER.debug(
            "%s: setCircuitPower for %d: %s", self._address, circuit_id, enable
        )

        ppas = pd303_pb2.ProtoPushAndSet()
        sta = getattr(
            ppas.load_incre_info.hall1_incre_info, "ch" + str(circuit_id + 1) + "_sta"
        )
        sta.load_sta = (
            pd303_pb2.LOAD_CH_POWER_ON if enable else pd303_pb2.LOAD_CH_POWER_OFF
        )
        sta.ctrl_mode = pd303_pb2.RLY_HAND_CTRL_MODE
        payload = ppas.SerializeToString()
        packet = Packet(0x21, 0x0B, 0x0C, 0x21, payload, 0x01, 0x01, 0x13)

        await self._conn.sendPacket(packet)

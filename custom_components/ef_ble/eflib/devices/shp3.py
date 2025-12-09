from collections.abc import Sequence
from dataclasses import dataclass

from ..commands import TimeCommands
from ..devicebase import AdvertisementData, BLEDevice, DeviceBase
from ..packet import Packet
from ..pb import pd303_pb2
from ..props import (
    Field,
    ProtobufProps,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)
from ..props.enums import IntFieldValue
from ..props.protobuf_field import TransformIfMissing


pb_time = proto_attr_mapper(pd303_pb2.ProtoTime)
pb_push_set = proto_attr_mapper(pd303_pb2.ProtoPushAndSet)


class ControlStatus(IntFieldValue):
    UNKNOWN = -1
    OFF = 0
    DISCHARGE = 1
    CHARGE = 2
    EMERGENCY_STOP = 3
    STANDBY = 4


class ForceChargeStatus(IntFieldValue):
    UNKNOWN = -1
    OFF = 0
    ON = 1


class PVStatus(IntFieldValue):
    UNKNOWN = -1
    NONE = 0
    LV = 1
    HV = 2
    LV_AND_HV = 3


@dataclass
class CircuitPowerField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_watt)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 2) if value and len(value) > self.idx else None


@dataclass
class CircuitCurrentField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_curr)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 4) if value and len(value) > self.idx else None


@dataclass
class ChannelPowerField(
    repeated_pb_field_type(list_field=pb_time.watt_info.ch_watt)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 2) if value and len(value) > self.idx else None


def _errors(error_codes: pd303_pb2.ErrCode):
    return [
        e for e in error_codes.err_code
        if e != b"\x00\x00\x00\x00\x00\x00\x00\x00"
    ] if error_codes and error_codes.err_code else []


class Device(DeviceBase, ProtobufProps):
    """
    Smart Home Panel 3 (experimental)

    Control paths exist but are fail-closed by default.
    """

    SN_PREFIX = b"HR63"
    NAME_PREFIX = "EF-SHP-32"

    NUM_OF_CIRCUITS = 32
    NUM_OF_CHANNELS = 3

    # ------------------------------------------------------------------
    # Global power
    # ------------------------------------------------------------------

    in_use_power = pb_field(pb_time.watt_info.all_hall_watt)

    grid_power = pb_field(
        pb_time.watt_info.grid_watt,
        TransformIfMissing(lambda v: v if v is not None else 0.0),
    )

    battery_level = pb_field(
        pb_push_set.backup_incre_info.backup_bat_per
    )

    errors = pb_field(pb_push_set.backup_incre_info.errcode, _errors)
    error_count = Field[int]()
    error_happened = Field[bool]()

    # ------------------------------------------------------------------
    # Circuits 1–32
    # ------------------------------------------------------------------

    for i in range(32):
        locals()[f"circuit_power_{i+1}"] = CircuitPowerField(i)
        locals()[f"circuit_current_{i+1}"] = CircuitCurrentField(i)

    del i

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    channel_power_1 = ChannelPowerField(0)
    channel_power_2 = ChannelPowerField(1)
    channel_power_3 = ChannelPowerField(2)

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------

    @staticmethod
    def check(sn: str) -> bool:
        return sn.startswith(Device.SN_PREFIX)

    def __init__(
        self,
        ble_dev: BLEDevice,
        adv_data: AdvertisementData,
        sn: str,
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

        # HARD SAFETY GATE:
        # this must be turned on manually once validated
        self._enable_circuit_control = False

    # ------------------------------------------------------------------
    # Packet parsing
    # ------------------------------------------------------------------

    async def data_parse(self, packet: Packet) -> bool:
        processed = False
        self.reset_updated()

        prev_error_count = self.error_count

        if packet.src == 0x0B and packet.cmdSet == 0x0C:
            if packet.cmdId == 0x01:
                await self._conn.replyPacket(packet)
                self.update_from_bytes(pd303_pb2.ProtoTime, packet.payload)
                processed = True

            elif packet.cmdId in (0x20, 0x21):
                await self._conn.replyPacket(packet)
                self.update_from_bytes(
                    pd303_pb2.ProtoPushAndSet,
                    packet.payload,
                )
                processed = True

        elif (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            if not packet.payload:
                self._time_commands.async_send_all()
            processed = True

        elif packet.src == 0x35 and packet.cmdSet == 0x35:
            processed = True

        self.error_count = len(self.errors) if self.errors is not None else None

        if (
            self.error_count is not None
            and prev_error_count is not None
            and self.error_count > prev_error_count
        ):
            self.error_happened = True

        for field_name in self.updated_fields:
            try:
                self.update_callback(field_name)
                self.update_state(field_name, getattr(self, field_name))
            except Exception:
                self._logger.exception(
                    "%s: %s: Failed updating field %s",
                    self.address,
                    self.name,
                    field_name,
                )

        return processed

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    async def set_config_flag(self, enable: bool):
        self._logger.debug("%s: setConfigFlag: %s", self._address, enable)

        ppas = pd303_pb2.ProtoPushAndSet()
        ppas.is_get_cfg_flag = enable

        payload = ppas.SerializeToString()
        packet = Packet(0x21, 0x0B, 0x0C, 0x21, payload, 0x01, 0x01, 0x13)

        await self._conn.sendPacket(packet)

    # ------------------------------------------------------------------
    # Control (guarded)
    # ------------------------------------------------------------------

    async def enable_circuit_control(self):
        """
        Explicit opt-in required to allow circuit control.
        Call this manually once SHP3 behavior is verified.
        """
        self._logger.warning(
            "%s: Enabling SHP3 circuit control – USE WITH CAUTION",
            self._address,
        )
        self._enable_circuit_control = True

    async def set_circuit_power(self, circuit_id: int, enable: bool):
        """
        Power on/off a circuit.

        circuit_id is 0-based (0–31).
        """
        if not self._enable_circuit_control:
            self._logger.warning(
                "%s: Circuit control blocked (circuit=%d enable=%s)",
                self._address,
                circuit_id,
                enable,
            )
            return

        if circuit_id < 0 or circuit_id >= self.NUM_OF_CIRCUITS:
            self._logger.error(
                "%s: Invalid circuit id %d",
                self._address,
                circuit_id,
            )
            return

        self._logger.info(
            "%s: setCircuitPower circuit=%d enable=%s",
            self._address,
            circuit_id + 1,
            enable,
        )

        # SHP2-style packet – assumed compatible pending validation
        ppas = pd303_pb2.ProtoPushAndSet()
        sta = getattr(
            ppas.load_incre_info.hall1_incre_info,
            f"ch{circuit_id + 1}_sta",
            None,
        )

        if sta is None:
            self._logger.error(
                "%s: Unable to resolve protobuf field for circuit %d",
                self._address,
                circuit_id,
            )
            return

        sta.load_sta = (
            pd303_pb2.LOAD_CH_POWER_ON
            if enable
            else pd303_pb2.LOAD_CH_POWER_OFF
        )
        sta.ctrl_mode = pd303_pb2.RLY_HAND_CTRL_MODE

        payload = ppas.SerializeToString()
        packet = Packet(0x21, 0x0B, 0x0C, 0x21, payload, 0x01, 0x01, 0x13)

        await self._conn.sendPacket(packet)

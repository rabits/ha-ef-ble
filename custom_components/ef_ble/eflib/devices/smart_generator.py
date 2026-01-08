from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import ge305_sys_pb2
from ..props import ProtobufProps, pb_field, proto_attr_mapper
from ..props.enums import IntFieldValue

pb = proto_attr_mapper(ge305_sys_pb2.DisplayPropertyUpload)


class FuelType(IntFieldValue):
    UNKNOWN = -1

    LNG = 1
    LPG = 2
    GASOLINE = 3  # original name: OIL


class EngineOpen(IntFieldValue):
    UNKNOWN = -1

    CLOSED = 0
    OPENED = 1
    CLOSING = 2


class SubBatteryState(IntFieldValue):
    UNKNOWN = -1

    IDLE = 0
    NO_INPUT = 1
    DISCHARGING = 2
    CHARGING = 3
    NORMAL_FULL = 4
    NORMAL_LOW_PRESSURE = 5


class PerformanceMode(IntFieldValue):
    UNKNOWN = -1

    ECO = 0
    PERFORMANCE = 1
    AUTO = 2


class LiquefiedGasType(IntFieldValue):
    UNKNOWN = -1

    LNG = 0
    LPG = 1


class LiquefiedGasUnit(IntFieldValue):
    UNKNOWN = -1

    LB = 0
    KG = 1

    # G = 2
    # LPH = 3
    # LPM = 4
    # GALH = 5
    # GALM = 6


class AbnormalState(IntFieldValue):
    UNKNOWN = -1

    NO = 0
    GASOLINE_LOW = 1  # original name: OIL_LOW


class Device(DeviceBase, ProtobufProps):
    """Smart Generator 3000 (Dual Fuel)"""

    SN_PREFIX = (b"G371",)
    NAME_PREFIX = "EF-GE"

    output_power = pb_field(pb.pow_out_sum_w)
    ac_output_power = pb_field(pb.pow_get_ac)

    engine_on = pb_field(
        pb.generator_engine_open,
        lambda x: EngineOpen.from_value(x) in [EngineOpen.OPENED, EngineOpen.CLOSING],
    )
    engine_state = pb_field(pb.generator_engine_open, EngineOpen.from_value)
    performance_mode = pb_field(pb.generator_perf_mode, PerformanceMode.from_value)

    self_start = pb_field(pb.cms_oil_self_start)

    fuel_type = pb_field(pb.generator_fuels_type, FuelType.from_value)
    liquefied_gas_unit = pb_field(
        pb.fuels_liquefied_gas_uint, LiquefiedGasUnit.from_value
    )
    liquefied_gas_value = pb_field(pb.fuels_liquefied_gas_val)
    liquefied_gas_consumption = pb_field(pb.fuels_liquefied_gas_consume_per_hour)
    lpg_level_monitoring = pb_field(pb.generator_lpg_monitor_en)

    generator_abnormal_state = pb_field(
        pb.generator_abnormal_state,
        lambda x: AbnormalState.from_value(x & 1),
    )

    sub_battery_power = pb_field(pb.pow_get_dc)
    sub_battery_soc = pb_field(pb.generator_sub_battery_soc)
    sub_battery_state = pb_field(
        pb.generator_sub_battery_state, SubBatteryState.from_value
    )

    ac_port = pb_field(pb.ac_out_open)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

    @classmethod
    def check(cls, sn):
        return sn.startswith(cls.SN_PREFIX)

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet):
        processed = False
        self.reset_updated()

        if packet.src == 0x08 and packet.cmdSet == 0xFE and packet.cmdId == 0x15:
            self.update_from_bytes(ge305_sys_pb2.DisplayPropertyUpload, packet.payload)
            processed = True
        elif (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def _send_config_packet(self, message: ge305_sys_pb2.ConfigWrite):
        payload = message.SerializeToString()
        packet = Packet(0x20, 0x08, 0xFE, 0x11, payload, 0x01, 0x01, 0x13)
        await self._conn.sendPacket(packet)

    async def enable_ac_port(self, enabled: bool):
        await self._send_config_packet(
            ge305_sys_pb2.ConfigWrite(cfg_ac_out_open=enabled)
        )

    async def enable_self_start(self, enabled: bool):
        await self._send_config_packet(
            ge305_sys_pb2.ConfigWrite(cfg_generator_self_on=enabled)
        )

    async def enable_engine_on(self, enabled: bool):
        value = EngineOpen.OPENED if enabled else EngineOpen.CLOSED
        await self._send_config_packet(
            ge305_sys_pb2.ConfigWrite(cfg_generator_engine_open=value.value)
        )

    async def enable_lpg_level_monitoring(self, enabled: bool):
        await self._send_config_packet(
            ge305_sys_pb2.ConfigWrite(
                cfg_generator_lpg_monitor_en=enabled,
                cfg_fuels_liquefied_gas_uint=self.liquefied_gas_unit,
                cfg_fuels_liquefied_gas_val=self.liquefied_gas_value,
            )
        )

    async def set_liquefied_gas_unit(self, value: LiquefiedGasUnit):
        gas_value = None
        if self.liquefied_gas_value is not None:
            if (
                self.liquefied_gas_unit is LiquefiedGasUnit.KG
                and value is LiquefiedGasUnit.LB
            ):
                gas_value = round(self.liquefied_gas_value * 2.2, 1)
            elif (
                self.liquefied_gas_unit is LiquefiedGasUnit.LB
                and value is LiquefiedGasUnit.KG
            ):
                gas_value = round(self.liquefied_gas_value / 2.2, 1)

        await self._send_config_packet(
            ge305_sys_pb2.ConfigWrite(
                cfg_fuels_liquefied_gas_uint=value.value,
                cfg_fuels_liquefied_gas_val=gas_value,
            )
        )

    async def set_liquefied_gas_value(self, value: float):
        await self._send_config_packet(
            ge305_sys_pb2.ConfigWrite(
                cfg_fuels_liquefied_gas_val=value,
                cfg_fuels_liquefied_gas_uint=self.liquefied_gas_unit,
            )
        )
        return True

    async def set_engine_open(self, engine_open: EngineOpen):
        if engine_open is EngineOpen.CLOSING:
            return

        await self._send_config_packet(
            ge305_sys_pb2.ConfigWrite(cfg_generator_engine_open=engine_open.value)
        )

    async def set_performance_mode(self, performance_mode: PerformanceMode):
        await self._send_config_packet(
            ge305_sys_pb2.ConfigWrite(cfg_generator_perf_mode=performance_mode.value)
        )

from dataclasses import dataclass

from ..commands import TimeCommands
from ..devicebase import AdvertisementData, BLEDevice, DeviceBase
from ..packet import Packet
from ..pb import yj751_sys_pb2
from ..props import (
    ProtobufProps,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)

pb_heartbeat = proto_attr_mapper(yj751_sys_pb2.AppShowHeartbeatReport)
pb_bp_info = proto_attr_mapper(yj751_sys_pb2.BpInfoReport)


@dataclass
class _BatteryLevel(
    repeated_pb_field_type(
        list_field=pb_bp_info.bp_info, value_field=lambda x: x.bp_soc, per_item=True
    )
):
    battery_no: int

    def get_value(self, item: yj751_sys_pb2.BPInfo) -> int | None:
        return item.bp_soc if item.bp_no == self.battery_no else None


class Device(DeviceBase, ProtobufProps):
    """Delta Pro Ultra"""

    SN_PREFIX = b"Y711"
    NAME_PREFIX = "EF-YJ"

    battery_level = pb_field(pb_heartbeat.soc)

    lv_solar_power = pb_field(pb_heartbeat.in_lv_mppt_pwr, lambda x: round(x, 2))
    hv_solar_power = pb_field(pb_heartbeat.in_hv_mppt_pwr, lambda x: round(x, 2))

    input_power = pb_field(pb_heartbeat.watts_in_sum)
    output_power = pb_field(pb_heartbeat.watts_out_sum)

    battery_1_battery_level = _BatteryLevel(1)
    battery_2_battery_level = _BatteryLevel(2)
    battery_3_battery_level = _BatteryLevel(3)
    battery_4_battery_level = _BatteryLevel(4)
    battery_5_battery_level = _BatteryLevel(5)

    ac_l1_1_out_power = pb_field(pb_heartbeat.out_ac_l1_1_pwr)
    ac_l1_2_out_power = pb_field(pb_heartbeat.out_ac_l1_2_pwr)
    ac_l2_1_out_power = pb_field(pb_heartbeat.out_ac_l2_1_pwr)
    ac_l2_2_out_power = pb_field(pb_heartbeat.out_ac_l2_2_pwr)
    ac_tt_out_power = pb_field(pb_heartbeat.out_ac_tt_pwr)
    ac_l14_out_power = pb_field(pb_heartbeat.out_ac_l14_pwr)
    ac_5p8_out_power = pb_field(pb_heartbeat.out_ac_5p8_pwr)

    @staticmethod
    def check(sn):
        return sn.startswith(Device.SN_PREFIX)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)

    async def data_parse(self, packet: Packet) -> bool:
        """Process the incoming notifications from the device"""

        processed = False
        self.reset_updated()

        if packet.src == 0x02 and packet.cmdSet == 0x02:
            if packet.cmdId == 0x01:  # Ping
                await self._conn.replyPacket(packet)
                self._logger.debug(
                    "%s: %s: Parsed data: %r", self.address, self.name, packet
                )
                self.update_from_bytes(
                    yj751_sys_pb2.AppShowHeartbeatReport, packet.payload
                )
                # self._logger.debug("DPU AppShowHeartbeatReport: \n %s", str(p))

                processed = True
            elif packet.cmdId == 0x04:
                await self._conn.replyPacket(packet)
                self.update_from_bytes(yj751_sys_pb2.BpInfoReport, packet.payload)
                # self._logger.debug("DPU BpInfoReport: \n %s", str(p))

                self.update_from_bytes(
                    yj751_sys_pb2.AppShowHeartbeatReport, packet.payload
                )
                processed = True
        elif packet.src == 0x35 and packet.cmdSet == 0x35 and packet.cmdId == 0x20:
            self._logger.debug(
                "%s: %s: Ping received: %r", self.address, self.name, packet
            )
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

        for prop_name in self.updated_fields:
            self.update_callback(prop_name)

        return processed

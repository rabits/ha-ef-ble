from collections.abc import Callable
from typing import Any, cast, overload

from google.protobuf.message import Message

from ..devicebase import DeviceBase
from ..packet import Packet
from ..pb import (
    jt_s1_edev_pb2,
    jt_s1_ev_pb2,
    jt_s1_heatingrod_pb2,
    jt_s1_heatpump_pb2,
    jt_s1_sys_pb2,
)
from ..props import (
    Field,
    FieldGroup,
    ProtobufProps,
    field_group,
    item_key,
    pb_field,
    pb_field_group,
    proto_attr_mapper,
    repeated_pb_field,
    repeated_pb_field_type,
)
from ..props.enums import IntFieldValue
from ..props.protobuf_field import proto_attr_name
from ..props.transforms import pnegative, ppositive

MAX_BATTERY_PACKS = 4

pb_heartbeat = proto_attr_mapper(jt_s1_sys_pb2.HeartbeatReport)
pb_energy_stream_report = proto_attr_mapper(jt_s1_sys_pb2.EnergyStreamReport)
pb_bp_heart = proto_attr_mapper(jt_s1_sys_pb2.BpHeartbeatReport)
pb_bp_sta = proto_attr_mapper(jt_s1_sys_pb2.BpStaReport)
pb_mppt_pv = proto_attr_mapper(jt_s1_sys_pb2.MpptPVInfo)

# The panel reports each phase under its own sub-message rather than a repeated field,
# so a phase group is one accessor per phase instead of an indexed path
_PHASES = (pb_heartbeat.pcs_a_phase, pb_heartbeat.pcs_b_phase, pb_heartbeat.pcs_c_phase)


class WorkMode(IntFieldValue):
    WORKMODE_SELFUSE = 0
    WORKMODE_TOU = 1
    WORKMODE_BACKUP = 2
    WORKMODE_DBG = 3
    WORKMODE_AC_MAKEUP = 4
    WORKMODE_DRM_MODE = 5
    WORKMODE_REMOTE_SCHED = 6
    WORKMODE_STANDBY_MODE = 7
    WORKMODE_SOC_CALIB = 8
    WORKMODE_TIMER_MODE = 9
    WORKMODE_FCR_MODE = 10
    WORKMODE_THIRD_MODE = 11
    WORKMODE_AI_SCHEDULE = 12
    WORKMODE_KRAKEN = 13
    UNKNOWN = -1


class BmsSysState(IntFieldValue):
    PRE_POWER_ON_STATE = 0
    CFM_POWER_ON_STATE = 1
    NORMAL_STATE = 2
    POWER_OFF_STATE = 3
    SLEEP_STATE = 4
    UNKNOWN = -1


class BmsRunStaDef(IntFieldValue):
    PB_BMS_STATE_SHUTDOWN = 0
    PB_BMS_STATE_NORMAL = 1
    PB_BMS_STATE_CHARGEABLE = 2
    PB_BMS_STATE_DISCHARGEABLE = 3
    PB_BMS_STATE_FAULT = 4
    UNKNOWN = -1


class _MpptPv(
    repeated_pb_field_type(
        list_field=pb_heartbeat.mppt_heart_beat,
        value_field=lambda item: item.mppt_pv[0].vol,
        per_item=True,
    )
):
    """One attribute of the `idx`th MPPT string, which the device reports in order"""

    idx: int
    item_attr: Any

    def get_value(self, item: jt_s1_sys_pb2.MpptStaReport) -> float | None:
        if self.idx > len(item.mppt_pv):
            return None
        return getattr(item.mppt_pv[self.idx - 1], proto_attr_name(self.item_attr))


@overload
def _bp_group[T_ATTR](
    item_attr: T_ATTR, name_template: str
) -> "FieldGroup[T_ATTR]": ...


@overload
def _bp_group[T_ATTR, T_OUT](
    item_attr: T_ATTR, name_template: str, transform: Callable[[T_ATTR], T_OUT]
) -> "FieldGroup[T_OUT]": ...


def _bp_group(
    item_attr: Any, name_template: str, transform: Callable[[Any], Any] | None = None
) -> "FieldGroup[Any]":
    """One field per battery pack, each reading the pack that names itself as its own"""
    return field_group(
        lambda idx: repeated_pb_field(
            pb_bp_heart.bp_heart_beat,
            item_attr,
            transform,
            where=item_key(pb_bp_sta.bp_dsrc, idx),
        ),
        MAX_BATTERY_PACKS,
        name_template=name_template,
    )


def _phase_group[T_ATTR](
    attrs: tuple[T_ATTR, ...], name_template: str
) -> "FieldGroup[T_ATTR]":
    return field_group(
        lambda idx: pb_field(attrs[idx - 1]), len(attrs), name_template=name_template
    )


def mppt_group[T_ATTR](
    item_attr: T_ATTR, count: int, name_template: str
) -> "FieldGroup[T_ATTR]":
    """Per-string MPPT fields; the Plus reports one string more than the rest"""
    return field_group(
        lambda idx: cast("Field[T_ATTR]", _MpptPv(idx, item_attr)),
        count,
        name_template=name_template,
    )


class PowerOceanBase(DeviceBase, ProtobufProps):
    EMS_REPORTS: dict[int, type[Message]] = {}

    extra_battery_name = "PowerOcean Battery Pack"

    load_system = pb_field(pb_energy_stream_report.sys_load_pwr)

    grid_import_power = pb_field(pb_energy_stream_report.sys_grid_pwr, ppositive())
    grid_export_power = pb_field(pb_energy_stream_report.sys_grid_pwr, pnegative())
    pv_power_sum = pb_field(pb_energy_stream_report.mppt_pwr)
    battery_input_power = pb_field(pb_energy_stream_report.bp_pwr, ppositive())
    battery_output_power = pb_field(pb_energy_stream_report.bp_pwr, pnegative())
    battery_remaining_energy = pb_field(pb_heartbeat.bp_remain_watth)

    # The message carries three, but a model only drives as many as it has strings
    pv_power = pb_field_group(
        pb_energy_stream_report.pv1_pwr, "pv{n}_pwr", 2, name_template="pv_power_{n}"
    )

    grid_meter_power = pb_field(pb_heartbeat.pcs_meter_power)
    inverter_power = pb_field(pb_heartbeat.pcs_act_pwr)
    battery_power_setpoint = pb_field(pb_heartbeat.ems_bp_power)

    # A pack is present exactly when it reports itself, which is what the config flow
    # reads to decide which packs to expose
    battery_enabled = _bp_group(
        pb_bp_sta.bp_dsrc, "battery_{n}_enabled", lambda _dsrc: True
    )

    battery_pack_current = _bp_group(pb_bp_sta.bp_amp, "battery_{n}_current")
    battery_error_code = _bp_group(pb_bp_sta.bp_err_code, "battery_{n}_error_code")
    battery_environment_temperature = _bp_group(
        pb_bp_sta.bp_env_temp, "battery_{n}_environment_temperature"
    )
    battery_max_cell_temperature = _bp_group(
        pb_bp_sta.bp_max_cell_temp, "battery_{n}_max_cell_temperature"
    )
    battery_min_cell_temperature = _bp_group(
        pb_bp_sta.bp_min_cell_temp, "battery_{n}_min_cell_temperature"
    )
    battery_pack_input_power = _bp_group(
        pb_bp_sta.bp_pwr, "battery_{n}_input_power", ppositive()
    )
    battery_pack_output_power = _bp_group(
        pb_bp_sta.bp_pwr, "battery_{n}_output_power", pnegative()
    )
    battery_pack_remaining_energy = _bp_group(
        pb_bp_sta.bp_remain_watth, "battery_{n}_remaining_energy"
    )
    battery_battery_level = _bp_group(pb_bp_sta.bp_soc, "battery_{n}_battery_level")
    battery_health = _bp_group(pb_bp_sta.bp_soh, "battery_{n}_health")
    battery_pack_voltage = _bp_group(pb_bp_sta.bp_vol, "battery_{n}_voltage")
    battery_cycles = _bp_group(pb_bp_sta.bp_cycles, "battery_{n}_cycles")
    battery_system_state = _bp_group(
        pb_bp_sta.bp_sys_state, "battery_{n}_system_state", BmsSysState.from_value
    )
    battery_bms_run_state = _bp_group(
        pb_bp_sta.bms_run_sta, "battery_{n}_bms_run_state", BmsRunStaDef.from_value
    )

    phase_voltage = _phase_group(tuple(p.vol for p in _PHASES), "l{n}_voltage")
    phase_current = _phase_group(tuple(p.amp for p in _PHASES), "l{n}_current")
    phase_power = _phase_group(tuple(p.act_pwr for p in _PHASES), "l{n}_power")
    phase_reactive_power = _phase_group(
        tuple(p.react_pwr for p in _PHASES), "l{n}_reactive_power"
    )
    phase_apparent_power = _phase_group(
        tuple(p.apparent_pwr for p in _PHASES), "l{n}_apparent_power"
    )

    pv_voltage = mppt_group(pb_mppt_pv.vol, 2, "pv_voltage_{n}")
    pv_current = mppt_group(pb_mppt_pv.amp, 2, "pv_current_{n}")

    @classmethod
    def check(cls, sn: bytes):
        return sn[:3] in cls.SN_PREFIX

    @property
    def device(self):
        model = ""
        match self._sn[:4]:
            case "HJ31":
                model = "10 kW"
            case "HJ35":
                model = "6 kW"
            case "HJ36":
                model = "8 kW"
            case "HJ37":
                model = "12 kW"
            case "J321":
                model = "Single Phase"
            case "J32A":
                model = "Single Phase 3 kW"
            case "J32B":
                model = "Single Phase 3.68 kW"
            case "J32C":
                model = "Single Phase 4.6 kW"
            case "J32D":
                model = "Single Phase 5 kW"
            case "J32E":
                model = "Single Phase 6 kW"
            case "R372":
                model = "Plus 3 Phase"
            case "HC31":
                model = "DC Fit"
        return f"PowerOcean {model}".strip()

    async def packet_parse(self, data: bytes):
        return Packet.from_bytes(data, xor_payload=True)

    async def data_parse(self, packet: Packet):
        self.reset_updated()

        match packet.src, packet.cmd_set, packet.cmd_id:
            case 0x60, 0x60, 0x01:
                report = jt_s1_sys_pb2.HeartbeatReport
            case 0x60, 0x60, 0x03:
                report = jt_s1_sys_pb2.ErrorChangeReport
            case 0x60, 0x60, 0x07:
                report = jt_s1_sys_pb2.BpHeartbeatReport
            case 0x60, 0x60, (0x08 | 0x11):
                report = self.EMS_REPORTS.get(packet.cmd_id)
            case 0x60, 0x60, 0x21:
                report = jt_s1_sys_pb2.EnergyStreamReport
            case 0x60, 0x60, 0x27:
                report = jt_s1_sys_pb2.EmsPVInvEnergyStreamReport
            case 0x60, 0xD1, 0x08:  # EV
                report = jt_s1_ev_pb2.EVChargingParamReport
            case 0x60, 0xD1, 0x21:
                report = jt_s1_ev_pb2.EVChargingEnergyStreamReport
            case 0x60, 0xD3, 0x01:  # heat pump
                report = jt_s1_heatpump_pb2.HPUIReport
            case 0x60, 0xD4, 0x08:  # heating rod
                report = jt_s1_heatingrod_pb2.HRChargingParamReport
            case 0x60, 0xD4, 0x21:
                report = jt_s1_heatingrod_pb2.HeatingRodEnergyStreamShow
            case 0x60, 0xF1, 0x21:  # edev
                report = jt_s1_edev_pb2.EDevEnergyStreamShow
            case _:
                report = None

        if report is not None:
            self.update_from_bytes(report, packet.payload)
        elif not self._is_known_unhandled(packet):
            self._logger.info(
                "Unknown packet: src=%d, cmd_set=%d, cmd_id=%d:\nPacket=%s",
                packet.src,
                packet.cmd_set,
                packet.cmd_id,
                packet,
            )

        self._notify_updated()

        return report is not None

    @staticmethod
    def _is_known_unhandled(packet: Packet) -> bool:
        cmd_id = packet.cmd_id
        match packet.src, packet.cmd_set:
            case _, 0xFE:
                return cmd_id == 0x10
            case 0x60, 0x60:
                return cmd_id in {
                    10, 11, 12, 13, 14, 17, 22, 24, 25, 26, 34, 35, 36, 37, 41, 50,
                    98, 99, 100, 101, 102, 103, 105, 106, 107, 109, 112, 121, 124,
                    125, 126, 127, 132, 133, 137, 138, 143, 144, 145, 147, 148, 151,
                    152, 153,
                }  # fmt: skip
            case 0x60, 0xD1:  # EV
                return cmd_id in {2, 97, 98, 99, 100, 101, 103}
            case 0x60, 0xD3:  # heat pump
                return cmd_id in {2, 99, 100, 102}
            case 0x60, 0xD4:  # heating rod
                return cmd_id in {2, 99, 101}
            case 0x60, 0xE0:  # ecology_dev
                return cmd_id in {1, 36, 38, 106, 107}
            case 0x60, 0xE1:  # parallel_lan
                return cmd_id in {97, 98}
            case 0x60, 0xF0:  # edev
                return cmd_id in {2, 97, 98, 99}
            case 0x60, 0xF1:  # edev
                return cmd_id in {1, 3, 4, 5, 36, 100, 101, 102, 106, 108, 113}
            case 0x03, 0x32:  # eco
                return cmd_id == 62
            case 0x35, 0x35:
                return cmd_id in {13, 113, 170}
            case _:
                return False

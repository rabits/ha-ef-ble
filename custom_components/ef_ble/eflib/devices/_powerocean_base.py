import logging
from abc import abstractmethod
from collections.abc import Sequence

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
    ProtobufProps,
    field_group,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)
from ..props.enums import IntFieldValue

_LOGGER = logging.getLogger(__name__)

MAX_BATTERY_PACKS = 4

pb_heartbeat = proto_attr_mapper(jt_s1_sys_pb2.HeartbeatReport)
pb_energy_stream_report = proto_attr_mapper(jt_s1_sys_pb2.EnergyStreamReport)
pb_bp_heart = proto_attr_mapper(jt_s1_sys_pb2.BpHeartbeatReport)

# The panel reports each phase under its own sub-message rather than a repeated field
_PHASE_ACCESSORS = (
    pb_heartbeat.pcs_a_phase,
    pb_heartbeat.pcs_b_phase,
    pb_heartbeat.pcs_c_phase,
)


def _from_pb_enum[T: IntFieldValue](cls: type[T], value: int) -> T:
    try:
        return cls(value)
    except ValueError:
        _LOGGER.debug("Encountered invalid value %s for %s", value, cls.__name__)
        return cls.UNKNOWN


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

    @classmethod
    def from_mode(cls, mode: int):
        return _from_pb_enum(cls, mode)


class BmsSysState(IntFieldValue):
    PRE_POWER_ON_STATE = 0
    CFM_POWER_ON_STATE = 1
    NORMAL_STATE = 2
    POWER_OFF_STATE = 3
    SLEEP_STATE = 4
    UNKNOWN = -1

    @classmethod
    def from_mode(cls, mode: int):
        return _from_pb_enum(cls, mode)


class BmsRunStaDef(IntFieldValue):
    PB_BMS_STATE_SHUTDOWN = 0
    PB_BMS_STATE_NORMAL = 1
    PB_BMS_STATE_CHARGEABLE = 2
    PB_BMS_STATE_DISCHARGEABLE = 3
    PB_BMS_STATE_FAULT = 4
    UNKNOWN = -1

    @classmethod
    def from_mode(cls, mode: int):
        return _from_pb_enum(cls, mode)


class _BpValue(repeated_pb_field_type(pb_bp_heart.bp_heart_beat, per_item=True)):
    """One attribute of the battery pack that reports itself as `idx`"""

    idx: int
    attr: str

    def get_value(self, item: jt_s1_sys_pb2.BpStaReport) -> int | float | None:
        if item.bp_dsrc != self.idx:
            return None
        return getattr(item, self.attr, None)


class _BpState(repeated_pb_field_type(pb_bp_heart.bp_heart_beat, per_item=True)):
    """An enum-valued attribute of the battery pack that reports itself as `idx`"""

    idx: int
    attr: str
    state: type[BmsSysState] | type[BmsRunStaDef]

    def get_value(self, item: jt_s1_sys_pb2.BpStaReport) -> IntFieldValue | None:
        if item.bp_dsrc != self.idx:
            return None
        return self.state.from_mode(getattr(item, self.attr))


class _MpptPv(repeated_pb_field_type(pb_heartbeat.mppt_heart_beat, per_item=True)):
    """One attribute of the `idx`th MPPT string, which the device reports in order"""

    idx: int
    attr: str

    def get_value(self, item: jt_s1_sys_pb2.MpptStaReport) -> float | None:
        if self.idx > len(item.mppt_pv):
            return None
        return getattr(item.mppt_pv[self.idx - 1], self.attr, None)


def _bp_group(attr: str, name_template: str):
    return field_group(
        lambda idx: _BpValue(idx, attr),
        MAX_BATTERY_PACKS,
        name_template=name_template,
    )


def _bp_state_group(
    attr: str, state: type[BmsSysState] | type[BmsRunStaDef], name_template: str
):
    return field_group(
        lambda idx: _BpState(idx, attr, state),
        MAX_BATTERY_PACKS,
        name_template=name_template,
    )


def _phase_group(attr: str, name_template: str):
    return field_group(
        lambda idx: pb_field(getattr(_PHASE_ACCESSORS[idx - 1], attr)),
        len(_PHASE_ACCESSORS),
        name_template=name_template,
    )


def mppt_group(attr: str, count: int, name_template: str):
    """Per-string MPPT fields; the Plus reports one string more than the rest"""
    return field_group(
        lambda idx: _MpptPv(idx, attr), count, name_template=name_template
    )


# Sentinel for the EMS change report: its message type differs between the standard and
# Plus models, so each subclass decodes it in `process_ems_change_report`
_EMS_CHANGE_REPORT = object()

# (src, cmd_set) -> cmd_id -> protobuf message decoded from the payload
_REPORTS: dict[tuple[int, int], dict[int, object]] = {
    (0x60, 0x60): {
        0x01: jt_s1_sys_pb2.HeartbeatReport,
        0x03: jt_s1_sys_pb2.ErrorChangeReport,
        0x07: jt_s1_sys_pb2.BpHeartbeatReport,
        0x08: _EMS_CHANGE_REPORT,
        0x11: _EMS_CHANGE_REPORT,
        0x21: jt_s1_sys_pb2.EnergyStreamReport,
        0x25: _EMS_CHANGE_REPORT,
        0x27: jt_s1_sys_pb2.EmsPVInvEnergyStreamReport,
    },
    (0x60, 0xD1): {  # EV
        0x08: jt_s1_ev_pb2.EVChargingParamReport,
        0x21: jt_s1_ev_pb2.EVChargingEnergyStreamReport,
    },
    (0x60, 0xD3): {  # heat pump
        0x01: jt_s1_heatpump_pb2.HPUIReport,
    },
    (0x60, 0xD4): {  # heating rod
        0x08: jt_s1_heatingrod_pb2.HRChargingParamReport,
        0x21: jt_s1_heatingrod_pb2.HeatingRodEnergyStreamShow,
    },
    (0x60, 0xF1): {  # edev
        0x21: jt_s1_edev_pb2.EDevEnergyStreamShow,
    },
}

# Packets the device sends that carry nothing we expose; listing them keeps the log free
# of noise while still reporting genuinely new message ids
# fmt: off
_UNHANDLED: dict[tuple[int, int], frozenset[int]] = {
    (0x60, 0x60): frozenset({
        10, 11, 12, 13, 14, 24, 25, 26, 34, 35, 36, 41, 50, 98, 99, 100, 101, 102,
        103, 105, 106, 107, 109, 112, 121, 124, 125, 126, 127, 132, 133, 137, 138,
        143, 144, 145, 147, 148, 151, 152, 153,
    }),
    (0x60, 0xD1): frozenset({2, 97, 98, 99, 100, 101, 103}),  # EV
    (0x60, 0xD3): frozenset({2, 99, 100, 102}),  # heat pump
    (0x60, 0xD4): frozenset({2, 99, 101}),  # heating rod
    (0x60, 0xE0): frozenset({1, 36, 38, 106, 107}),  # ecology_dev
    (0x60, 0xE1): frozenset({97, 98}),  # parallel_lan
    (0x60, 0xF0): frozenset({2, 97, 98, 99}),  # edev
    (0x60, 0xF1): frozenset({1, 3, 4, 5, 36, 100, 101, 102, 106, 108, 113}),  # edev
    (0x03, 0x32): frozenset({62}),  # eco
    (0x35, 0x35): frozenset({13, 113, 170}),
}
# fmt: on

_MODELS = {
    "HJ31": "10 kW",
    "HJ35": "6 kW",
    "HJ36": "8 kW",
    "HJ37": "12 kW",
    "J321": "Single Phase",
    "J32A": "Single Phase 3 kW",
    "J32B": "Single Phase 3.68 kW",
    "J32C": "Single Phase 4.6 kW",
    "J32D": "Single Phase 5 kW",
    "J32E": "Single Phase 6 kW",
    "R372": "Plus 3 Phase",
    "HC31": "DC Fit",
}


class PowerOceanBase(DeviceBase, ProtobufProps):
    SN_PREFIX: Sequence[bytes]

    extra_battery_name = "PowerOcean Battery Pack"

    load_system = pb_field(pb_energy_stream_report.sys_load_pwr)
    grid_power = pb_field(pb_energy_stream_report.sys_grid_pwr)
    power_mppt = pb_field(pb_energy_stream_report.mppt_pwr)
    battery_power = pb_field(pb_energy_stream_report.bp_pwr)
    batteries_remaining_power = pb_field(pb_heartbeat.bp_remain_watth)

    pv_main_power = field_group(
        lambda idx: pb_field(getattr(pb_energy_stream_report, f"pv{idx}_pwr")),
        3,
        name_template="pv_main_power_{n}",
    )

    pcs_meter_power = pb_field(pb_heartbeat.pcs_meter_power)
    pcs_active_power = pb_field(pb_heartbeat.pcs_act_pwr)
    batteries_ems_power = pb_field(pb_heartbeat.ems_bp_power)

    battery_current = _bp_group("bp_amp", "battery_{n}_current")
    battery_error_code = _bp_group("bp_err_code", "battery_{n}_error_code")
    battery_environment_temperature = _bp_group(
        "bp_env_temp", "battery_{n}_environment_temperature"
    )
    battery_max_cell_temperature = _bp_group(
        "bp_max_cell_temp", "battery_{n}_max_cell_temperature"
    )
    battery_min_cell_temperature = _bp_group(
        "bp_min_cell_temp", "battery_{n}_min_cell_temperature"
    )
    battery_pack_power = _bp_group("bp_pwr", "battery_{n}_power")
    battery_remaining_power = _bp_group(
        "bp_remain_watth", "battery_{n}_remaining_power"
    )
    battery_battery_level = _bp_group("bp_soc", "battery_{n}_battery_level")
    battery_health = _bp_group("bp_soh", "battery_{n}_health")
    battery_voltage = _bp_group("bp_vol", "battery_{n}_voltage")
    battery_cycles = _bp_group("bp_cycles", "battery_{n}_cycles")
    battery_system_state = _bp_state_group(
        "bp_sys_state", BmsSysState, "battery_{n}_system_state"
    )
    battery_bms_run_state = _bp_state_group(
        "bms_run_sta", BmsRunStaDef, "battery_{n}_bms_run_state"
    )

    phase_voltage = _phase_group("vol", "l{n}_voltage")
    phase_current = _phase_group("amp", "l{n}_current")
    phase_power = _phase_group("act_pwr", "l{n}_power")
    phase_reactive_power = _phase_group("react_pwr", "l{n}_reactive_power")
    phase_apparent_power = _phase_group("apparent_pwr", "l{n}_apparent_power")

    pv_voltage = mppt_group("vol", 2, "pv_voltage_{n}")
    pv_current = mppt_group("amp", 2, "pv_current_{n}")
    pv_power = mppt_group("pwr", 2, "pv_power_{n}")

    @classmethod
    def check(cls, sn: bytes):
        return sn[:3] in cls.SN_PREFIX

    @property
    def device(self):
        return f"PowerOcean {_MODELS.get(self._sn[:4], '(Unidentified)')}"

    async def packet_parse(self, data: bytes):
        return Packet.from_bytes(data, xor_payload=True)

    def _report_for(self, packet: Packet):
        return _REPORTS.get((packet.src, packet.cmd_set), {}).get(packet.cmd_id)

    def _is_known_unhandled(self, packet: Packet) -> bool:
        if packet.cmd_set == 0xFE and packet.cmd_id == 0x10:
            return True
        return packet.cmd_id in _UNHANDLED.get((packet.src, packet.cmd_set), ())

    async def data_parse(self, packet: Packet):
        self.reset_updated()

        report = self._report_for(packet)
        if report is _EMS_CHANGE_REPORT:
            self.process_ems_change_report(packet)
        elif report is not None:
            self.update_from_bytes(report, packet.payload)
        elif not self._is_known_unhandled(packet):
            self._logger.info(
                "Unknown packet: src=%d, cmd_set=%d, cmd_id=%d:\nPacket=%s",
                packet.src,
                packet.cmd_set,
                packet.cmd_id,
                packet,
            )

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return report is not None

    @abstractmethod
    def process_ems_change_report(self, packet: Packet):
        """Decode the EMS change report in the message type this model sends"""

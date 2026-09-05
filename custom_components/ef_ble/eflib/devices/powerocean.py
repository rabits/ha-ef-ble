from ..pb import jt_s1_sys_pb2
from ..props import pb_field, proto_attr_mapper
from ._powerocean_base import PowerOceanBase, WorkMode

pb_ems_change_report = proto_attr_mapper(jt_s1_sys_pb2.EmsChangeReport)

# Covers every PowerOcean model that is neither Plus nor Pro; the standard range is
# large and all of its members speak the same jt_s1 message set


class Device(PowerOceanBase):
    """PowerOcean"""

    SN_PREFIX = (b"J32", b"HJ3", b"HC3")  # 1-phase, 3-phase, DC-Fit
    NAME_PREFIX = "EF-J32"
    EMS_CHANGE_REPORT = jt_s1_sys_pb2.EmsChangeReport

    ems_work_mode = pb_field(pb_ems_change_report.ems_word_mode, WorkMode.from_value)

    battery_level = pb_field(pb_ems_change_report.bp_soc)
    batteries_total_charge_energy = pb_field(pb_ems_change_report.bp_total_chg_energy)
    batteries_total_discharge_energy = pb_field(
        pb_ems_change_report.bp_total_dsg_energy
    )
    batteries_online_count = pb_field(pb_ems_change_report.bp_online_sum)

    pv_fault_code_1 = pb_field(pb_ems_change_report.mppt1_fault_code)
    pv_warning_code_1 = pb_field(pb_ems_change_report.mppt1_warning_code)
    pv_fault_code_2 = pb_field(pb_ems_change_report.mppt2_fault_code)
    pv_warning_code_2 = pb_field(pb_ems_change_report.mppt2_warning_code)

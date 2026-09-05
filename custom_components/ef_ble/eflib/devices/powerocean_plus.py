from ..packet import Packet
from ..pb import re307_sys_pb2
from ..props import pb_field, proto_attr_mapper
from ._powerocean_base import PowerOceanBase, WorkMode, mppt_group

pb_ems_state_change_report = proto_attr_mapper(re307_sys_pb2.EmsStateChangeReport)
pb_ems_change_report = proto_attr_mapper(re307_sys_pb2.EmsChangeReport)

# The Plus reports state through EmsStateChangeReport; its own EmsChangeReport carries
# different data than the message of that name the standard models send


class Device(PowerOceanBase):
    """PowerOcean Plus"""

    SN_PREFIX = (b"R37",)
    NAME_PREFIX = "EF-R37"

    ems_work_mode = pb_field(pb_ems_change_report.ems_word_mode, WorkMode.from_mode)

    battery_level = pb_field(pb_ems_state_change_report.bp_soc)
    batteries_total_charge_energy = pb_field(
        pb_ems_state_change_report.bp_total_chg_energy
    )
    batteries_total_discharge_energy = pb_field(
        pb_ems_state_change_report.bp_total_dsg_energy
    )
    batteries_online_count = pb_field(pb_ems_state_change_report.bp_online_sum)

    # Only the Plus drives a third string
    pv_voltage = mppt_group("vol", 3, "pv_voltage_{n}")
    pv_current = mppt_group("amp", 3, "pv_current_{n}")
    pv_power = mppt_group("pwr", 3, "pv_power_{n}")

    pv_fault_code_1 = pb_field(pb_ems_state_change_report.mppt1_fault_code)
    pv_warning_code_1 = pb_field(pb_ems_state_change_report.mppt1_warning_code)
    pv_fault_code_2 = pb_field(pb_ems_state_change_report.mppt2_fault_code)
    pv_warning_code_2 = pb_field(pb_ems_state_change_report.mppt2_warning_code)
    pv_fault_code_3 = pb_field(pb_ems_state_change_report.mppt3_fault_code)
    pv_warning_code_3 = pb_field(pb_ems_state_change_report.mppt3_warning_code)

    # Command ids 0x08, 0x11 and 0x25 all arrive on the same message here, and without a
    # test device it is unconfirmed which of EmsChangeReport / EmsStateChangeReport each
    # one carries
    def process_ems_change_report(self, packet: Packet):
        self.update_from_bytes(re307_sys_pb2.EmsChangeReport, packet.payload)

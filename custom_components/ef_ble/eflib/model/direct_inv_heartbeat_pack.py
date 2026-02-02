from typing import Annotated

from .base import RawData


class DirectInvHeartbeatPack(RawData):
    err_code: Annotated[int, "I", "errCode"]
    sys_ver: Annotated[int, "I", "sysVer"]
    charger_type: Annotated[int, "B", "chargerType"]
    input_watts: Annotated[int, "H", "inputWatts"]
    output_watts: Annotated[int, "H", "outputWatts"]
    inv_type: Annotated[int, "B", "invType"]
    inv_out_vol: Annotated[int, "I", "invOutVol"]
    inv_out_amp: Annotated[int, "I", "invOutAmp"]
    inv_out_freq: Annotated[int, "B", "invOutFreq"]


class DirectInvDeltaHeartbeatPack(DirectInvHeartbeatPack):
    ac_in_vol: Annotated[int, "I", "acInVol"]
    ac_in_amp: Annotated[int, "I", "acInAmp"]
    ac_in_freq: Annotated[int, "B", "acInFreq"]
    out_temp: Annotated[int, "H", "outTemp"]
    dc_in_vol: Annotated[int, "I", "dcInVol"]
    dc_in_amp: Annotated[int, "I", "dcInAmp"]
    dc_in_temp: Annotated[int, "H", "dcInTemp"]
    fan_state: Annotated[int, "B", "fanState"]
    cfg_ac_enabled: Annotated[int, "B", "cfgAcEnabled"]
    cfg_ac_xboost: Annotated[int, "B", "cfgAcXboost"]
    cfg_ac_out_voltage: Annotated[int, "I", "cfgAcOutVoltage"]
    cfg_ac_out_freq: Annotated[int, "B", "cfgAcOutFreq"]
    cfg_ac_work_mode: Annotated[int, "B", "cfgAcWorkMode"]
    cfg_pause_flag: Annotated[int, "B", "cfgPauseFlag"]
    ac_dip_switch: Annotated[int, "B", "acDipSwitch"]
    cfg_fast_chg_watts: Annotated[int, "H", "cfgFastChgWatts"]
    cfg_slow_chg_watts: Annotated[int, "H", "cfgSlowChgWatts"]
    standby_mins: Annotated[int, "H", "standbyMins"]
    discharge_type: Annotated[int, "B", "dischargeType"]
    ac_passby_auto_en: Annotated[int, "B", "acPassbyAutoEn"]
    pr_balance_mode: Annotated[int, "B", "prBalanceMode"]
    ac_chg_rated_power: Annotated[int, "H", "acChgRatedPower"]
    cfg_gfci_enable: Annotated[int, "B", "cfgGfciEnable"]


class DirectInvRiverHeartbeatPackBase(DirectInvHeartbeatPack):
    inv_in_vol: Annotated[int, "I", "invInVol"]
    inv_in_amp: Annotated[int, "I", "invInAmp"]
    inv_in_freq: Annotated[int, "B", "invInFreq"]
    out_temp: Annotated[int, "H", "outTemp"]
    dc_in_vol: Annotated[int, "I", "dcInVol"]
    dc_in_amp: Annotated[int, "I", "dcInAmp"]
    in_temp: Annotated[int, "H", "inTemp"]
    fan_state: Annotated[int, "B", "fanState"]
    cfg_ac_enabled: Annotated[int, "B", "cfgAcEnabled"]
    cfg_ac_xboost: Annotated[int, "B", "cfgAcXboost"]
    cfg_ac_out_voltage: Annotated[int, "I", "cfgAcOutVoltage"]
    cfg_ac_out_freq: Annotated[int, "B", "cfgAcOutFreq"]
    cfg_ac_chg_mode_flg: Annotated[int, "B", "cfgAcChgModeFlg"]


class DirectInvRiverHeartbeatPack(DirectInvRiverHeartbeatPackBase):
    cfg_standby_min: Annotated[int, "H", "cfgStandbyMin"]
    cfg_fan_mode: Annotated[int, "B", "cfgFanMode"]
    ac_auto_config: Annotated[int, "B", "acAutoConfig"]


class DirectInvRiverMiniHeartbeatPack(DirectInvRiverHeartbeatPackBase):
    soc: Annotated[int, "B", "soc"]
    vol: Annotated[int, "I", "vol"]
    amp: Annotated[int, "I", "amp"]
    temp: Annotated[int, "H", "temp"]
    bat_err_code: Annotated[int, "I", "batErrCode"]
    remain_cap: Annotated[int, "I", "remainCap"]
    full_cap: Annotated[int, "I", "fullCap"]
    cycles: Annotated[int, "H", "cycles"]
    max_charge_soc: Annotated[int, "B", "maxChargeSoc"]
    f_soc: Annotated[int, "B", "fSoc"]
    standby_mins: Annotated[int, "H", "standbyMins"]

from typing import Annotated

from .base import RawData


class BaseMpptHeart(RawData):
    fault_code: Annotated[int, "I", "faultCode"]
    sw_ver: Annotated[str, "4s", "swVer"]
    in_vol: Annotated[int, "I", "inVol"]
    in_amp: Annotated[int, "I", "inAmp"]
    in_watts: Annotated[int, "H", "inWatts"]
    out_val: Annotated[int, "I", "outVal"]
    out_amp: Annotated[int, "I", "outAmp"]
    out_watts: Annotated[int, "H", "outWatts"]
    mppt_temp: Annotated[int, "h", "mpptTemp"]
    xt60_chg_type: Annotated[int, "B", "xt60ChgType"]
    cfg_chg_type: Annotated[int, "B", "cfgChgType"]
    chg_type: Annotated[int, "B", "chgType"]
    chg_state: Annotated[int, "B", "chgState"]
    dcdc_12v_vol: Annotated[int, "I", "dcdc12VVol"]
    dcdc_12v_amp: Annotated[int, "I", "dcdc12VAmp"]
    dcdc_12v_watts: Annotated[int, "H", "dcdc12VWatts"]
    car_out_vol: Annotated[int, "I", "carOutVol"]
    car_out_amp: Annotated[int, "I", "carOutAmp"]
    car_out_watts: Annotated[int, "H", "carOutWatts"]
    car_temp: Annotated[int, "h", "carTemp"]
    car_state: Annotated[int, "B", "carState"]
    dc24v_temp: Annotated[int, "h", "dc24vTemp"]
    dc24v_state: Annotated[int, "B", "dc24vState"]
    chg_pause_flag: Annotated[int, "B", "chgPauseFlag"]
    cfg_dc_chg_current: Annotated[int, "I", "cfgDcChgCurrent"]


class Mr330MpptHeart(BaseMpptHeart):
    beep_state: Annotated[int, "B", "beepState"]
    cfg_ac_enabled: Annotated[int, "B", "cfgAcEnabled"]
    cfg_ac_xboost: Annotated[int, "B", "cfgAcXboost"]
    cfg_ac_out_voltage: Annotated[int, "I", "cfgAcOutVoltage"]
    cfg_ac_out_freq: Annotated[int, "B", "cfgAcOutFreq"]
    cfg_chg_watts: Annotated[int, "H", "cfgChgWatts"]
    ac_standby_mins: Annotated[int, "H", "acStandbyMins"]
    discharge_type: Annotated[int, "B", "dischargeType"]
    car_standby_mins: Annotated[int, "H", "carStandbyMins"]
    power_standby_mins: Annotated[int, "H", "powerStandbyMins"]
    screen_standby_mins: Annotated[int, "H", "screenStandbyMins"]
    pay_flag: Annotated[int, "H", "payFlag"]
    reserved: Annotated[bytes, "8s", "res"]

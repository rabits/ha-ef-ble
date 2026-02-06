from typing import Annotated

from .base import RawData


class BasePdHeart(RawData):
    model: Annotated[int, "B", "model"]
    error_code: Annotated[bytes, "4s", "errorCode"]
    sys_ver: Annotated[bytes, "4s", "sysVer"]
    wifi_ver: Annotated[bytes, "4s", "wifiVer"]
    wifi_auto_recovery: Annotated[int, "B", "wifiAutoRecovery"]
    soc: Annotated[int, "B", "soc"]
    watts_out_sum: Annotated[int, "H", "wattsOutSum"]
    watts_in_sum: Annotated[int, "H", "wattsInSum"]
    remain_time: Annotated[int, "i", "remainTime"]

    quiet_mode: Annotated[int, "B", "quietMode"]
    dc_out_state: Annotated[int, "B", "dcOutState"]

    usb1_watt: Annotated[int, "B", "usb1Watt"]
    usb2_watt: Annotated[int, "B", "usb2Watt"]
    qc_usb1_watt: Annotated[int, "B", "qcUsb1Watt"]
    qc_usb2_watt: Annotated[int, "B", "qcUsb2Watt"]
    typec1_watts: Annotated[int, "B", "typeC1Watts"]
    typec2_watts: Annotated[int, "B", "typeC2Watts"]
    typec1_temp: Annotated[int, "B", "typeC1Temp"]
    typec2_temp: Annotated[int, "B", "typeC2Temp"]

    car_state: Annotated[int, "B", "carState"]
    car_watts: Annotated[int, "B", "carWatts"]
    car_temp: Annotated[int, "B", "carTemp"]

    standby_min: Annotated[int, "H", "standbyMin"]
    lcd_off_sec: Annotated[int, "H", "lcdOffSec"]
    lcd_brightness: Annotated[int, "B", "lcdBrightness"]

    dc_chg_power: Annotated[int, "I", "dcChgPower"]
    sun_chg_power: Annotated[int, "I", "sunChgPower"]
    ac_chg_power: Annotated[int, "I", "acChgPower"]
    dc_dsg_power: Annotated[int, "I", "dcDsgPower"]
    ac_dsg_power: Annotated[int, "I", "acDsgPower"]

    usb_used_time: Annotated[int, "I", "usbUsedTime"]
    usb_qc_used_time: Annotated[int, "I", "usbQcUsedTime"]
    type_c_used_time: Annotated[int, "I", "typeCUsedTime"]
    car_used_time: Annotated[int, "I", "carUsedTime"]
    inv_used_time: Annotated[int, "I", "invUsedTime"]
    dc_in_used_time: Annotated[int, "I", "dcInUsedTime"]
    mppt_used_time: Annotated[int, "I", "mpptUsedTime"]


class Mr330PdHeart(BasePdHeart):
    reverser: Annotated[int, "H", "reverser"]
    screen_state: Annotated[bytes, "14s", "screenState"]
    ext_rj45_port: Annotated[int, "B", "extRj45Port"]
    ext_3p8_port: Annotated[int, "B", "ext3P8Port"]
    ext_4p8_port: Annotated[int, "B", "ext4P8Port"]
    syc_chg_dsg_state: Annotated[int, "B", "sycChgDsgState"]
    wifi_rssi: Annotated[int, "B", "wifiRssi"]
    wireless_watts: Annotated[int, "B", "wirelessWatts"]


class Mr330PdHeartDelta2(Mr330PdHeart):
    charge_type: Annotated[int, "B", "chargeType"]
    ac_input_watts: Annotated[int, "H", "acInputWatts"]
    ac_output_watts: Annotated[int, "H", "acOutputWatts"]
    dc_pv_input_watts: Annotated[int, "H", "dcPvInputWatts"]
    dc_pv_output_watts: Annotated[int, "H", "dcPvOutputWatts"]
    cfg_ac_enabled: Annotated[int, "B", "cfgAcEnabled"]

    pv_priority: Annotated[int, "B", "pvPriority"]
    ac_auto_on: Annotated[int, "B", "acAutoOn"]  # or acAutoOutConfig based on flag

    watthis_config: Annotated[int, "B", "watthisConfig"]
    bp_power_soc: Annotated[int, "B", "bppowerSoc"]
    hysteresis_soc: Annotated[int, "B", "hysteresisSoc"]
    reply_switchcnt: Annotated[int, "I", "replySwitchcnt"]
    ac_auto_out_config: Annotated[int, "B", "acAutoOutConfig"]
    min_auto_soc: Annotated[int, "B", "minAutoSoc"]
    ac_auto_out_pause: Annotated[int, "B", "acAutoOutPause"]

    schedule_id: Annotated[int, "I", "scheduleId"]
    heartbeat_duration: Annotated[int, "I", "heartbeatDuration"]
    bkw_watts_in_power: Annotated[int, "H", "bkwWattsInPower"]
    input_power_limit_flag: Annotated[int, "B", "inputPowerLimitFlag"]
    ac_charge_flag: Annotated[int, "B", "acChargeFlag"]
    cloud_ctrl_en: Annotated[int, "B", "cloudCtrlEn"]
    redun_charge_flag: Annotated[int, "B", "redunChargeFlag"]


class Mr330PdHeartRiver2(Mr330PdHeart):
    ac_auto_out_config: Annotated[int, "B", "acAutoOutConfig"]
    min_auto_soc: Annotated[int, "H", "minAutoSoc"]
    ac_auto_out_pause: Annotated[int, "H", "acAutoOutPause"]
    watthis_config: Annotated[int, "B", "watthisConfig"]
    bp_power_soc: Annotated[int, "B", "bppowerSoc"]
    hysteresis_soc: Annotated[int, "B", "hysteresisSoc"]
    reply_switchcnt: Annotated[int, "I", "replySwitchcnt"]


class Mr350PdHeartbeatCore(BasePdHeart):
    bms_kit_state: Annotated[int, "H", "bmsKitState"]
    other_kit_state: Annotated[int, "B", "otherKitState"]
    reversed: Annotated[int, "H", "reversed"]
    sys_chg_flag: Annotated[int, "B", "sysChgFlag"]
    wifi_rssi: Annotated[int, "B", "wifiRssi"]
    wireless_watts: Annotated[int, "B", "wirelessWatts"]
    screen_state: Annotated[bytes, "14s", "screenState"]


class Mr350PdHeartbeatDelta2Max(Mr350PdHeartbeatCore):
    first_xt150_watts: Annotated[int, "H", "firstXt150Watts"]
    second_xt150_watts: Annotated[int, "H", "secondXT150Watts"]
    inv_in_watts: Annotated[int, "H", "invInWatts"]
    inv_out_watts: Annotated[int, "H", "invOutWatts"]
    pv1_charge_type: Annotated[int, "B", "pv1ChargeType"]
    pv1_charge_watts: Annotated[int, "H", "pv1ChargeWatts"]
    pv2_charge_type: Annotated[int, "B", "pv2ChargeType"]
    pv2_charge_watts: Annotated[int, "H", "pv2ChargeWatts"]
    pv_charge_prio_set: Annotated[int, "B", "pvChargePrioSet"]
    ac_auto_on_cfg_set: Annotated[int, "B", "acAutoOnCfgSet"]

    ac_auto_out_config: Annotated[int, "B", "acAutoOutConfig"]
    main_ac_out_soc: Annotated[int, "B", "mainAcOutSoc"]
    ac_auto_out_pause: Annotated[int, "B", "acAutoOutPause"]

    watthisconfig: Annotated[int, "B", "watthisconfig"]
    bp_power_soc: Annotated[int, "B", "bppowerSoc"]
    hysteresis_add: Annotated[int, "B", "hysteresisAdd"]
    relayswitchcnt: Annotated[int, "I", "relayswitchcnt"]


class Mr350PdHeartbeatDeltaPro(Mr350PdHeartbeatCore):
    first_xt150_watts: Annotated[int, "H", "firstXt150Watts"]
    second_xt150_watts: Annotated[int, "H", "secondXT150Watts"]
    inv_in_watts: Annotated[int, "H", "invInWatts"]
    inv_in_type: Annotated[int, "B", "invInType"]
    inv_out_watts: Annotated[int, "H", "invOutWatts"]
    inv_out_type: Annotated[int, "B", "invOutType"]
    pv1_charge_watts: Annotated[int, "H", "pv1ChargeWatts"]
    pv1_charge_type: Annotated[int, "B", "pv1ChargeType"]
    anderson_power: Annotated[int, "H", "andersonPower"]
    pv_charge_prio_set: Annotated[int, "B", "pvChargePrioSet"]
    ac_auto_on_cfg_set: Annotated[int, "B", "acAutoOnCfgSet"]
    ac_auto_out_config: Annotated[int, "B", "acAutoOutConfig"]
    main_ac_out_soc: Annotated[int, "B", "mainAcOutSoc"]
    ac_auto_out_pause: Annotated[int, "B", "acAutoOutPause"]

    watthisconfig: Annotated[int, "B", "watthisconfig"]
    bp_power_soc: Annotated[int, "B", "bppowerSoc"]
    hysteresis_add: Annotated[int, "B", "hysteresisAdd"]
    relayswitchcnt: Annotated[int, "I", "relayswitchcnt"]

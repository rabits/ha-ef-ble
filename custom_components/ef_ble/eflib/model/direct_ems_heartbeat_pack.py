from typing import Annotated

from .base import RawData


class DirectEmsDeltaHeartbeatPack(RawData):
    chg_state: Annotated[int, "B", "chgState"]
    chg_cmd: Annotated[int, "B", "chgCmd"]
    dsg_cmd: Annotated[int, "B", "dsgCmd"]
    chg_vol: Annotated[int, "I", "chgVol"]
    chg_amp: Annotated[int, "I", "chgAmp"]
    fan_level: Annotated[int, "B", "fanLevel"]
    max_charge_soc: Annotated[int, "B", "maxChargeSoc"]
    bms_model: Annotated[int, "B", "bmsModel"]
    lcd_show_soc: Annotated[int, "B", "lcdShowSoc"]
    open_ups_flag: Annotated[int, "B", "openUpsFlag"]
    bms_warning_state: Annotated[int, "B", "bmsWarningState"]
    chg_remain_time: Annotated[int, "I", "chgRemainTime"]
    dsg_remain_time: Annotated[int, "I", "dsgRemainTime"]
    ems_is_normal_flag: Annotated[int, "B", "emsIsNormalFlag"]
    f32_lcd_show_soc: Annotated[float, "f", "f32LcdShowSoc"]
    bms_is_connt: Annotated[bytes, "3s", "bmsIsConnt"]
    max_available_num: Annotated[int, "B", "maxAvailableNum"]
    open_bms_idx: Annotated[int, "B", "openBmsIdx"]
    para_vol_min: Annotated[int, "I", "paraVolMin"]
    para_vol_max: Annotated[int, "I", "paraVolMax"]
    min_dsg_soc: Annotated[int, "B", "minDsgSoc"]
    open_oil_eb_soc: Annotated[int, "B", "openOilEbSoc"]
    close_oil_eb_soc: Annotated[int, "B", "closeOilEbSoc"]

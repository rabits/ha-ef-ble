from typing import Annotated

from .pd_heart import RawData


class DirectBmsMDeltaHeartbeatPack(RawData):
    num: Annotated[int, "B", "num"]
    type_: Annotated[int, "B", "type"]
    cell_id: Annotated[int, "B", "cellId"]
    err_code: Annotated[int, "I", "errCode"]
    sys_ver: Annotated[int, "I", "sysVer"]
    soc: Annotated[int, "B", "soc"]
    vol: Annotated[int, "I", "vol"]
    amp: Annotated[int, "I", "amp"]
    temp: Annotated[int, "B", "temp"]
    open_bms_idx: Annotated[int, "B", "openBmsIdx"]
    design_cap: Annotated[int, "I", "designCap"]
    remain_cap: Annotated[int, "I", "remainCap"]
    full_cap: Annotated[int, "I", "fullCap"]
    cycles: Annotated[int, "I", "cycles"]
    soh: Annotated[int, "B", "soh"]
    max_cell_vol: Annotated[int, "H", "maxCellVol"]
    min_cell_vol: Annotated[int, "H", "minCellVol"]
    max_cell_temp: Annotated[int, "B", "maxCellTemp"]
    min_cell_temp: Annotated[int, "B", "minCellTemp"]
    max_mos_temp: Annotated[int, "B", "maxMosTemp"]
    min_mos_temp: Annotated[int, "B", "minMosTemp"]
    bms_fault: Annotated[int, "B", "bmsFault"]
    bq_sys_stat_reg: Annotated[int, "B", "bqSysStatReg"]
    tag_chg_amp: Annotated[int, "I", "tagChgAmp"]
    f32_show_soc: Annotated[float, "f", "f32ShowSoc"]
    input_watts: Annotated[int, "I", "inputWatts"]
    output_watts: Annotated[int, "I", "outputWatts"]
    remain_time: Annotated[int, "I", "remainTime"]

from dataclasses import dataclass
from typing import Annotated

from .base import RawData


@dataclass
class WaveInfo(RawData):
    sn: Annotated[str, "16s", "sn"]
    product_type: Annotated[int, "H", "productType"]
    product_detail: Annotated[int, "H", "productDetail"]
    procedure_state: Annotated[int, "B", "procedureState"]
    app_version: Annotated[int, "I", "appVersion"]
    loader_version: Annotated[int, "I", "loaderVersion"]
    device_connt: Annotated[int, "B", "deviceConnt"]
    device_state: Annotated[int, "B", "deviceState"]
    cur_power: Annotated[int, "i", "curPower"]
    f32_soc: Annotated[float, "f", "f32Soc"]
    remain_percent: Annotated[int, "B", "remainPercent"]
    chg_amp: Annotated[int, "H", "chgAmp"]
    chg_vol: Annotated[int, "H", "chgVol"]

from dataclasses import field
from typing import Annotated, Self

from .base import RawData


class KitBaseInfo(RawData):
    avai_flag: Annotated[int, "B", "avaiFlag"]
    sn: Annotated[bytes, "16s", "sn"]
    product_type: Annotated[int, "H", "productType"]
    product_detail: Annotated[int, "H", "productDetail"]
    procedure_state: Annotated[int, "B", "procedureState"]
    app_version: Annotated[int, "I", "appVersion"]
    loader_version: Annotated[int, "I", "loaderVersion"]
    cur_real_power: Annotated[int, "I", "curRealPower"]
    f32_soc: Annotated[int, "I", "f32Soc"]
    soc: Annotated[int, "B", "soc"]


class AllKitDetailData(RawData):
    protocol_version: Annotated[int, "B", "protocolVersion"]
    available_data_len: Annotated[int, "H", "availableDataLen"]
    support_kit_max_num: Annotated[int, "H", "supportKitMaxNum"]

    kit_base_info: list[KitBaseInfo] = field(default_factory=list)

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        parsed = super().from_bytes(data)

        offset = parsed.SIZE

        for _ in range(parsed.support_kit_max_num):
            base_info = KitBaseInfo.from_bytes(data[offset:])
            parsed.kit_base_info.append(base_info)
            offset += base_info.SIZE
        return parsed

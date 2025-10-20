from dataclasses import dataclass
from typing import dataclass_transform


@dataclass_transform()
class RawData:
    def __init_subclass__(cls) -> None:
        dataclass(cls)

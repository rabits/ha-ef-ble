import struct
from dataclasses import dataclass, fields
from typing import Annotated, ClassVar, Self, dataclass_transform, get_args, get_origin


@dataclass_transform()
class RawData:
    _STRUCT_FMT: ClassVar[str]
    SIZE: int

    def __init_subclass__(cls) -> None:
        dataclass(cls)
        format_str = ["<"]

        for field in fields(cls):
            if get_origin(field.type) is Annotated:
                _, *metadata = get_args(field.type)
                format_str += metadata[0]

        cls._STRUCT_FMT = "".join(format_str)
        cls.SIZE = struct.calcsize(cls._STRUCT_FMT)

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        return cls(*cls.unpack(data))

    @classmethod
    def unpack(cls, data: bytes):
        return struct.unpack(cls._STRUCT_FMT, data[: cls.SIZE])

    @classmethod
    def list_from_bytes[T](cls: T, data: bytes) -> list[T]:
        raise ValueError("This class does not support decoding into lists")

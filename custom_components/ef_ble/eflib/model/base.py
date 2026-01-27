import struct
from dataclasses import dataclass, fields
from functools import cache
from inspect import get_annotations, getmro
from typing import Annotated, ClassVar, Self, dataclass_transform, get_args, get_origin


@dataclass_transform()
class RawData:
    r"""
    Class for handling fixed width binary format messages

    The format can be specified with fields using Annotated format as
    `Annotated[<type>, <struct_fmt_str>, <original_name>]` where type is a python type,
    struct_fmt_str is format character from python's `struct` library, see
    https://docs.python.org/3/library/struct.html#format-characters and original_name
    is the name from the original decompiled source code (optional).

    This class is also able to decode binary streams partially in case the data uses
    optional extensions. This works by going through the format in reverse and removing
    bytes from struct string one by one until the size matches the data size.

    Examples
    --------
    Here's an example on how define simple format:

        class DataFormat(RawData):
            data_int: Annotated[int, "I", "originalDataInt"]
            data_byte: Annotated[byte, "c", "original_data_byte"]
            data_str: Annotated[str, "4s", "originalDataStr"]

    Class can then be used like this
    >>> decoded = DataFormat.from_bytes(b"\x00\x00\x00\x00\x01\x41\x41\x41\x41")
    >>> print(decoded.data_int, decoded.data_byte, decoded.data_str)
    0, b"\x01", b"AAAA"

    This also works if you supply partial data
    >>> decoded = DataFormat.frombytes(b"\x00\x00\x00\x00")
    >>> print(decoded.data_int, decoded.data_byte, decoded.data_str)
    0, None, None
    """

    _STRUCT_FMT: ClassVar[str]
    SIZE: int

    def __init_subclass__(cls) -> None:
        # set byte order to litte-endian (or for subclasses, get the full format str
        # from parent)
        format_str = getattr(cls, "_FULL_STRUCT_FMT", ["<"])

        for name, annotation in get_annotations(cls).items():
            if get_origin(annotation) is Annotated:
                # get struct format character from type as
                #  Annotated[type, struct_fmt, optional]
                _, *metadata = get_args(annotation)
                if not metadata:
                    continue
                format_str.append(metadata[0])

                # by setting all defaults to None, we can construct the class only
                # partially - messages can be defined with optional extensions depending
                # on firmware versions
                setattr(cls, name, None)

        # make this a dataclass (dataclass is an inline operation)
        dataclass(cls)

        cls._FULL_STRUCT_FMT = format_str
        cls._STRUCT_FMT = "".join(format_str)
        cls.SIZE = struct.calcsize(cls._STRUCT_FMT)

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """
        Unpack bytes to an instance of this class

        Parameters
        ----------
        data
            Bytes to decode

        Returns
        -------
        Instance of this class decoded from data
        """
        return cls(*cls.unpack(data))

    @classmethod
    def unpack(cls, data: bytes):
        """
        Unpack binary data according to the fields defined in this class

        Parameters
        ----------
        data
            Bytes to decode

        Returns
        -------
        Tuple of unpacked data types
        """
        struct_fmt = cls._STRUCT_FMT
        size = cls.SIZE

        # data may not contain all of the extensions so if the size is less than we
        # expect, we try to remove format characters from the end of the format string
        # until it matches
        if (data_len := len(data)) < cls.SIZE:
            struct_fmt, size = cls._fit_struct_to_data(data_len)

        return struct.unpack(struct_fmt, data[:size])

    def pack(self):
        return struct.pack(
            self._STRUCT_FMT,
            *[getattr(self, field.name) for field in fields(self)],
        )

    @classmethod
    def list_from_bytes(cls, data: bytes) -> list[Self]:
        """
        Decode data into a list of instances of this class

        This method can be used to construct list of instances if the data contains
        multiple concatenated structures. It does not check whether the sizes match so
        check the caller has to it is the caller's responsibility.

        Parameters
        ----------
        data
            Bytes to decode into a list of instances

        """
        obj_1 = cls.from_bytes(data)
        obj_size = obj_1.SIZE
        ret_list = [obj_1]

        offset = obj_size

        if len(data[offset:]) > obj_1.SIZE:
            ret_list.append(cls.from_bytes(data[offset:]))
            offset += obj_size
        return ret_list

    @classmethod
    @cache
    def _fit_struct_to_data(cls, data_len: int):
        size = cls.SIZE
        i = 0
        reduced_fmt = "".join(cls._FULL_STRUCT_FMT)

        # here, we remove one byte at a time and check if the calculated size fits the
        # binary data for each loop - if it does, we return the reduced format that is
        # compatible with the data size and the resulting size
        while size > data_len:
            i += 1
            reduced_fmt = "".join(cls._FULL_STRUCT_FMT[:-i])
            size = struct.calcsize(reduced_fmt)

        return "".join(cls._FULL_STRUCT_FMT[:-i]), size

    @classmethod
    @cache
    def get_bases(cls):
        parents = []
        for parent in getmro(cls):
            if parent == RawData:
                break

            parents.append(parent)
        return parents

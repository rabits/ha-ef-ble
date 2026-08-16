import abc
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    cast,
    dataclass_transform,
    overload,
)

from google.protobuf.message import Message

from .protobuf_field import ProtobufField

if TYPE_CHECKING:
    from .protobuf_props import ProtobufProps


@dataclass_transform()
class ProtobufRepeatedField[T_ITEM, T_OUT](ProtobufField[T_OUT]):
    """
    Represents field for repeated protobuf fields

    Do not use this class directly - use `repeated_pb_field_type` for better typing
    """

    def __init_subclass__(cls) -> None:
        dataclass(cls, unsafe_hash=True)

    def get_list(self, value: Message) -> Sequence[Message]:
        """
        Get sequence from protobuf message

        Parameters
        ----------
        value
            Parsed protobuf message

        Returns
        -------
            Sequence of values accessed from protobuf message
        """
        list_attrs = self.pb_field.attrs
        if not list_attrs:
            raise ValueError(f"Received accessor with no attributes: '{self.pb_field}'")

        try:
            if not value.HasField(list_attrs[0]):
                return []
        except ValueError as e:
            if "not have presence" not in str(e):
                return []

        for attr in list_attrs:
            value = getattr(value, attr)

        return cast(Sequence[Message], value)

    @abc.abstractmethod
    def get_item(self, value: Sequence[T_ITEM]) -> T_OUT | None:
        """Process item from sequence returned from `get_list`"""

    def __set__(self, instance: "ProtobufProps", value: Sequence[Any]):
        if (item := self.get_item(value)) is None:
            return

        self._set_value(instance, item)


class ProtobufCompositeRepeatedField[T_ITEM, T_OUT](
    ProtobufRepeatedField[T_ITEM, T_OUT]
):
    def get_item(self, value: Sequence[T_ITEM]) -> T_OUT | None:
        for item in value:
            if (result := self.get_value(item)) is not None:
                return result
        return None

    @abc.abstractmethod
    def get_value(self, item: T_ITEM) -> T_OUT | None: ...


def _raise[T_IN](v: T_IN, exc: type[Exception]) -> T_IN:
    raise exc


@overload
def repeated_pb_field_type[T_ITEM, T_OUT](
    list_field: Sequence[T_ITEM],
    value_field: Callable[[T_ITEM], T_OUT] = lambda x: _raise(x, NotImplementedError),
    per_item: Literal[True] = True,
) -> type[ProtobufCompositeRepeatedField[T_ITEM, T_OUT]]: ...


@overload
def repeated_pb_field_type[T_ITEM, T_OUT](
    list_field: Sequence[T_ITEM],
    value_field: Callable[[T_ITEM], T_OUT] = lambda x: _raise(x, NotImplementedError),
    per_item: Literal[False] = False,
) -> type[ProtobufRepeatedField[T_ITEM, T_OUT]]: ...


def repeated_pb_field_type[T_ITEM, T_OUT](
    list_field: Sequence[T_ITEM],
    value_field: Callable[[T_ITEM], T_OUT] = lambda x: _raise(x, NotImplementedError),
    per_item: bool = False,
) -> (
    type[ProtobufRepeatedField[T_ITEM, T_OUT]]
    | type[ProtobufCompositeRepeatedField[T_ITEM, T_OUT]]
):
    """
    Create repeated field type from protobuf accessor repesenting sequence type

    Usage
    -----
    Assuming protobuf message looks like this
    ```
    message RecordType { int value = 1; }
    messsage SomeMessageType { repeated RecordType some_list = 1; }
    ```

    We can create a field that processes items like so
    ```
    pb = proto_attr_mapper(some_pb2.SomeMessageType)

    class SomeRepeatedField(
        repeated_field_type(
            list_field=pb.some_list,
            value_field=lambda x: x.value,
        )
    ):
        def get_item(self, value: Sequence[some_pb2.RecordType]):
            return value[1].value
    ```

    Returns
    -------
        Type of repeated protobuf message
    """
    if not per_item:

        class CustomRepeatedField(ProtobufRepeatedField[T_ITEM, T_OUT]):
            pb_field = list_field

        return CustomRepeatedField

    class CustomPerItemRepeatedField(ProtobufCompositeRepeatedField[T_ITEM, T_OUT]):
        pb_field = list_field

    return CustomPerItemRepeatedField

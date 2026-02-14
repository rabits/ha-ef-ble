from collections import defaultdict
from collections.abc import Callable
from functools import cached_property

from google.protobuf.message import Message

from .. import devicebase
from ..listeners import ListenerGroup, ListenerRegistry
from ..logging_util import LogOptions
from .protobuf_field import ProtobufField
from .repeated_protobuf_field import ProtobufRepeatedField
from .updatable_props import UpdatableProps

type MessageProcessedListener = Callable[[Message], None]


class _Listeners(ListenerRegistry):
    on_message_processed: ListenerGroup[MessageProcessedListener]


class ProtobufProps(UpdatableProps):
    """
    Mixin for augmenting device classes with properties parsed from protobuf messages

    This mixin provides method `update_from_message` that should be called for each
    incoming protobuf message and updates every defined `ProtobufField`.

    Usage
    -----
    ```
    pb = proto_attr_mapper(<protobuf_class>)

    class Device(DeviceBase, ProtobufProps):
        proto_field = pb_field(pb.field_from_message)

        def data_parse(self, packet):
            message = <protobuf_class>()
            message.ParseFromString(packet.payload)
            self.update_from_message(message)

            # self.updated_fields now holds all updated fields
            for field_name in self.updated_fields:
                self.update_state(field_name, getattr(self, field_name))
    ```

    """

    _repeated_field_map: dict[type[Message], dict[str, list[ProtobufRepeatedField]]] = (
        defaultdict(lambda: defaultdict(list))
    )
    _proto_listeners = _Listeners.create()

    @classmethod
    def add_repeated_field(cls, repeated_field: ProtobufRepeatedField):
        updated_field_map = cls._repeated_field_map.copy()
        updated_field_map[repeated_field.pb_field.message_type][
            repeated_field.pb_field.name
        ].append(repeated_field)
        cls._repeated_field_map = updated_field_map

    @cached_property
    def message_to_field(self) -> dict[type[Message], list[ProtobufField]]:
        field_map = defaultdict(list)
        for field in self._fields:
            if isinstance(field, ProtobufRepeatedField):
                continue

            if not isinstance(field, ProtobufField):
                continue

            field_map[field.pb_field.message_type].append(field)
        return field_map

    def reset_updated(self):
        self._processed_fields = []
        return super().reset_updated()

    def on_message_processed(self, listener: MessageProcessedListener):
        return self._proto_listeners.on_message_processed.add(listener)

    def update_from_message(self, message: Message, reset: bool = False):
        """
        Update defined fields values from provided message

        Parameters
        ----------
        message
            Protocol buffer message to update fields from
        """
        if reset:
            self.reset_updated()

        for field in self.message_to_field[type(message)]:
            setattr(self, field.public_name, message)

        for repeated_fields in self._repeated_field_map[type(message)].values():
            field_list = repeated_fields[0].get_list(message)
            if field_list is None:
                continue

            for field in repeated_fields:
                setattr(self, field.public_name, field_list)

        self._proto_listeners.on_message_processed(message)

    @cached_property
    def _log_message(self) -> Callable[[Message], None]:
        if not isinstance(self, devicebase.DeviceBase):
            return lambda _: None

        def _log_msg(msg: Message):
            return self._logger.log_filtered(
                LogOptions.DESERIALIZED_MESSAGES,
                "Message from %s, type: %s\n%s",
                self.device,
                msg.DESCRIPTOR.full_name,
                str(msg),
            )

        return _log_msg

    def update_from_bytes[T_MSG: Message](
        self,
        message_type: type[T_MSG],
        serialized_message: bytes,
        reset: bool = False,
    ) -> T_MSG:
        msg = message_type()
        msg.ParseFromString(serialized_message)
        self.update_from_message(msg, reset=reset)
        self._log_message(msg)
        return msg

    def __str__(self):
        field_values = []
        for field in self._fields:
            if hasattr(self, field.public_name):
                value = getattr(self, field.public_name)
                field_values.append(f"{field.public_name}={value}")

        class_name = self.__class__.__name__
        return f"{class_name}(\n  {',\n  '.join(field_values)}\n)"

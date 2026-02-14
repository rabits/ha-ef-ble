import abc
from collections import defaultdict
from collections.abc import Callable
from functools import cached_property
from typing import Literal, overload

from .. import devicebase
from ..connection import LogOptions
from ..listeners import ListenerGroup, ListenerRegistry
from ..model.base import RawData
from .raw_data_field import RawDataField
from .updatable_props import UpdatableProps

type MessageProcessedListener = Callable[[RawData], None]


class _Listeners(ListenerRegistry):
    on_message_processed: ListenerGroup[MessageProcessedListener]


class RawDataProps(UpdatableProps, abc.ABC):
    _raw_listeners = _Listeners.create()

    def update_from_data(self, data: RawData, reset: bool = False):
        if reset:
            self.reset_updated()

        for base in type(data).get_bases():
            for field in self._datatype_to_field[base]:
                setattr(self, field.public_name, data)

    @overload
    def update_from_bytes[T: RawData](
        self,
        data: type[T],
        payload: bytes,
        as_list: Literal[False] = False,
        reset: bool = False,
    ) -> T: ...

    @overload
    def update_from_bytes[T: RawData](
        self, data: type[T], payload: bytes, as_list: Literal[True], reset: bool = False
    ) -> list[T]: ...

    def on_message_processed(self, listener: MessageProcessedListener):
        return self._raw_listeners.on_message_processed.add(listener)

    def update_from_bytes[T: RawData](
        self, data: type[T], payload: bytes, as_list: bool = False, reset: bool = False
    ) -> T | list[T]:
        msgs = (
            data.list_from_bytes(data=payload)
            if as_list
            else [data.from_bytes(data=payload)]
        )

        for msg in msgs:
            self.update_from_data(msg, reset=reset)
            self._log_message(msg)
            self._raw_listeners.on_message_processed(msg)

        return msgs if as_list else msgs[0]

    @cached_property
    def _log_message(self) -> Callable[[RawData], None]:
        if not isinstance(self, devicebase.DeviceBase):
            return lambda _: None

        def _log_msg(msg: RawData):
            return self._logger.log_filtered(
                LogOptions.DESERIALIZED_MESSAGES,
                "Message from %s, type: %s\n%s",
                self.device,
                msg.__class__.__name__,
                str(msg),
            )

        return _log_msg

    @cached_property
    def _datatype_to_field(self) -> dict[type[RawData], list[RawDataField]]:
        field_map = defaultdict(list)
        for field in self._fields:
            if not isinstance(field, RawDataField):
                continue

            field_map[field.data_attr.message_type].append(field)
        return field_map

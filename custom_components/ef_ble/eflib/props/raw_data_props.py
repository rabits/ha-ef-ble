import abc
from collections import defaultdict
from functools import cached_property

from ..model.base import RawData
from .raw_data_field import RawDataField
from .updatable_props import UpdatableProps


class RawDataProps(UpdatableProps, abc.ABC):
    def update_from_data(self, data: RawData, reset: bool = False):
        if reset:
            self.reset_updated()

        for field in self._datatype_to_field[type(data)]:
            setattr(self, field.public_name, data)

    @cached_property
    def _datatype_to_field(self) -> dict[type[RawData], list[RawDataField]]:
        field_map = defaultdict(list)
        for field in self._fields:
            if not isinstance(field, RawDataField):
                continue

            field_map[field.data_attr.message_type].append(field)
        return field_map

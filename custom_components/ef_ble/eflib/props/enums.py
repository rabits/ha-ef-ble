import logging
from enum import IntEnum
from typing import Self

_LOGGER = logging.getLogger(__name__)


class IntFieldValue(IntEnum):
    @classmethod
    def from_value(cls, value: int) -> Self:
        try:
            return cls(value)
        except ValueError:
            _LOGGER.debug("Encountered invalid value %s for %s", value, cls.__name__)
            return cls.UNKNOWN

    @classmethod
    def str_from_value(cls, value: int):
        return cls.from_value(value).state_name

    @property
    def state_name(self):
        return self.name.lower()

    @classmethod
    def options(
        cls, include_unknown: bool = True, exclude: list["IntFieldValue"] = []
    ) -> list[str]:
        return [
            opt.name.lower()
            for opt in cls
            if (opt is not getattr(cls, "UNKNOWN", None) or include_unknown)
            and opt not in exclude
        ]

    def __repr__(self):
        return self.state_name

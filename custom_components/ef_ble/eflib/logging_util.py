import logging
from collections.abc import Mapping
from enum import Flag, auto
from functools import cached_property
from typing import TYPE_CHECKING, Any

import bleak

if TYPE_CHECKING:
    from .connection import Connection
    from .devicebase import DeviceBase


class SensitiveMaskingFilter(logging.Filter):
    def __init__(self, patterns: dict[str, str], name: str = "") -> None:
        super().__init__(name)
        self._patterns = patterns

    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        record.msg = self.mask_message(record.msg)
        record.name = self.mask_message(record.name)

        if isinstance(record.args, Mapping):
            record.args = {k: self.mask_message(v) for k, v in record.args.items()}
        elif record.args is not None:
            record.args = tuple(self.mask_message(v) for v in record.args)

        return True

    def mask_message(self, msg: Any):
        if not isinstance(msg, str):
            return msg

        for pattern, replacement in self._patterns.items():
            msg = msg.replace(pattern, replacement)
        return msg


class LogOptions(Flag):
    MASKED = auto()

    ENCRYPTED_PAYLOADS = auto()
    DECRYPTED_PAYLOADS = auto()
    PACKETS = auto()
    DESERIALIZED_MESSAGES = auto()

    CONNECTION_DEBUG = auto()
    BLEAK_DEBUG = auto()

    @property
    def enabled(self):
        return self & (
            LogOptions.ENCRYPTED_PAYLOADS
            | LogOptions.DECRYPTED_PAYLOADS
            | LogOptions.PACKETS
            | LogOptions.DESERIALIZED_MESSAGES
            | LogOptions.CONNECTION_DEBUG
        )


_BLEAK_LOGGER = logging.getLogger(bleak.__name__)
_ORIGINAL_BLEAK_LOG_LEVEL = _BLEAK_LOGGER.level


class MaskingLogger(logging.Logger):
    def __init__(self, logger: logging.Logger, patterns: dict[str, str]) -> None:
        self._logger = logger
        self._patterns = patterns
        self._options = LogOptions(0)

    @cached_property
    def _mask_filter(self):
        return SensitiveMaskingFilter(self._patterns)

    def __getattr__(self, name: str):
        return getattr(self._logger, name)

    @property
    def options(self):
        return self._options

    def set_options(self, options: LogOptions):
        self._options = options
        self._logger.setLevel(logging.DEBUG if options.enabled else logging.INFO)

        bleak_logger = logging.getLogger(bleak.__name__)
        if LogOptions.BLEAK_DEBUG in options:
            bleak_logger.setLevel(logging.DEBUG)
        elif bleak_logger.isEnabledFor(logging.DEBUG):
            bleak_logger.setLevel(_ORIGINAL_BLEAK_LOG_LEVEL)

        if LogOptions.MASKED not in options:
            self._logger.removeFilter(self._mask_filter)
            return

        self._logger.addFilter(self._mask_filter)

    def log_filtered(
        self,
        options: LogOptions,
        msg: object,
        *args: object,
        level: int = logging.DEBUG,
    ) -> None:
        if options in self._options:
            self._logger.log(level, msg, *args)


def _mask_sn(sn: str):
    return f"{sn[:4]}{'*' * len(sn[4:-4])}{sn[-4:]}"


def _mask_mac(mac_addr: str):
    return f"{mac_addr[:5]}:**:**:**:**"


def _mask_user_id(user_id: str):
    return f"{user_id[:4]}{'*' * len(user_id[4:])}"


class DeviceLogger(MaskingLogger):
    def __init__(self, device: "DeviceBase"):
        super().__init__(
            logging.getLogger(f"{device.__module__} - {device._address}"),
            patterns={
                device._address: _mask_mac(device._address),
                device._sn: _mask_sn(device._sn),
            },
        )


class ConnectionLogger(MaskingLogger):
    def __init__(self, connection: "Connection") -> None:
        super().__init__(
            logging.getLogger(f"{connection.__module__} - {connection._address}"),
            patterns={
                connection._address: _mask_mac(connection._address),
                connection._dev_sn: _mask_sn(connection._dev_sn),
                connection._user_id: _mask_user_id(connection._user_id),
            },
        )

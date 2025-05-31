import json
import logging
import re
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Flag, auto
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

import bleak

if TYPE_CHECKING:
    from .connection import Connection, ConnectionState
    from .devicebase import DeviceBase


class SensitiveMaskingFilter(logging.Filter):
    def __init__(
        self, mask_funcs: Sequence[Callable[[str], str | None]], name: str = ""
    ) -> None:
        super().__init__(name)
        self._mask_funcs = mask_funcs

    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        record.msg = self.mask_message(record.msg)
        record.name = self.mask_message(record.name)

        if isinstance(record.args, Mapping):
            record.args = {k: self.mask_message(v) for k, v in record.args.items()}
        elif record.args is not None:
            record.args = tuple(self.mask_message(v) for v in record.args)

        return True

    def mask_message(self, msg: Any):
        msg_str = msg
        if not isinstance(msg, str):
            msg_str = str(msg)

        replaced = False
        for func in self._mask_funcs:
            if replacement := func(msg_str):
                msg_str = replacement
                replaced = True
        return msg_str if replaced else msg

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, SensitiveMaskingFilter):
            return False
        return self.name == value.name


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

    @staticmethod
    def no_options():
        return LogOptions(0)


_BLEAK_LOGGER = logging.getLogger(bleak.__name__)
_ORIGINAL_BLEAK_LOG_LEVEL = _BLEAK_LOGGER.level


class MaskingLogger(logging.Logger):
    def __init__(
        self, logger: logging.Logger, mask_funcs: Sequence[Callable[[str], str | None]]
    ) -> None:
        self._logger = logger
        self._mask_funcs = mask_funcs
        self._options = LogOptions.no_options()

    @cached_property
    def _mask_filter(self):
        return SensitiveMaskingFilter(self._mask_funcs)

    def __getattr__(self, name: str):
        return getattr(self._logger, name)

    @property
    def options(self):
        return self._options

    def set_options(self, options: LogOptions):
        self._options = options
        self._logger.setLevel(logging.DEBUG if options.enabled else logging.INFO)

        if LogOptions.MASKED in options:
            for handler in logging.root.handlers:
                if self._mask_filter not in handler.filters:
                    handler.addFilter(self._mask_filter)

        bleak_logger = logging.getLogger(bleak.__name__)
        if LogOptions.BLEAK_DEBUG in options:
            bleak_logger.setLevel(logging.DEBUG)

        elif bleak_logger.isEnabledFor(logging.DEBUG):
            bleak_logger.setLevel(_ORIGINAL_BLEAK_LOG_LEVEL)

        if LogOptions.MASKED not in options:
            for handler in logging.root.handlers:
                if self._mask_filter in handler.filters:
                    handler.removeFilter(self._mask_filter)

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
    regex = re.compile(sn)

    def _mask(input: str):
        match = regex.search(input)
        if match:
            return f"{sn[:4]}{'*' * len(sn[4:-4])}{sn[-4:]}"
        return None

    return _mask


def _mask_mac(mac_addr: str):
    regex = re.compile(mac_addr.replace(":", "(.)"))

    def _mask(input: str):
        match = regex.search(input)
        if match:
            delim = match.group(1)
            return regex.sub(
                delim.join([mac_addr[:2], mac_addr[3:5], "**", "**", "**"]), input
            )
        return None

    return _mask


def _mask_user_id(user_id: str):
    regex = re.compile(user_id)

    def _mask(input: str):
        match = regex.search(input)
        if match:
            return f"{user_id[:4]}{'*' * len(user_id[4:])}"
        return None

    return _mask


class DeviceLogger(MaskingLogger):
    def __init__(self, device: "DeviceBase"):
        super().__init__(
            logging.getLogger(f"{device.__module__} - {device._address}"),
            mask_funcs=[_mask_mac(device._address), _mask_sn(device._sn)],
        )


class ConnectionLogger(MaskingLogger):
    def __init__(self, connection: "Connection") -> None:
        super().__init__(
            logging.getLogger(f"{connection.__module__} - {connection._address}"),
            mask_funcs=[
                _mask_mac(connection._address),
                _mask_sn(connection._dev_sn),
                _mask_user_id(connection._user_id),
            ],
        )


@dataclass
class ConnectionLog:
    name: str
    maxlen: int = 20
    cache_to_file: bool = False

    def __post_init__(self):
        self._history_start = time.time()

    @property
    def history(self) -> deque[dict[str, float | str]]:
        history = getattr(self, "_history", None)
        if history is None:
            self._history = deque(maxlen=self.maxlen)
        return self._history

    @staticmethod
    def cache_file_for(address: str):
        path = (
            Path(__file__).parent / ".cache" / f"{address.replace(':', '_')}_setup.log"
        )
        path.parent.mkdir(exist_ok=True)
        return path

    @property
    def _cache_path(self):
        return self.cache_file_for(self.name)

    def append(self, state: "ConnectionState", reason: str | None = None):
        entry: dict[str, float | str] = {
            "time": time.time() - self._history_start,
            "state": f"{state.name}",
        }

        if reason:
            entry["reason"] = reason

        self.history.append(entry)
        if self.cache_to_file:
            with self._cache_path.open("a") as f:
                f.write(f"{json.dumps(entry)}\n")

    def load_from_cache(self):
        if self._cache_path.exists():
            try:
                return [
                    json.loads(line)
                    for line in self._cache_path.read_text().splitlines()
                ]
            except:  # noqa: E722
                return []
        return []

    @staticmethod
    def clean_cache_for(address: str):
        ConnectionLog.cache_file_for(address).unlink(missing_ok=True)

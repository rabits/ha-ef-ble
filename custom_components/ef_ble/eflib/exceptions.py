class PacketParseError(Exception):
    """Error during parsing Packet"""


class EncPacketParseError(Exception):
    """Error during parsing EncPacket"""


class PacketReceiveError(Exception):
    """Error during receiving packet"""


class FailedToAuthenticate(Exception):
    """Failed to connect"""


class ConnectionTimeout(TimeoutError):
    """Connection timeout reached"""


class MaxConnectionAttemptsReached(Exception):
    """Device could not complete initial connection after maximum attempts"""

    def __init__(
        self, last_error: Exception | type[Exception] | None = None, attempts: int = 8
    ):
        super().__init__()
        self.last_error = last_error
        self.attempts = attempts


class MaxReconnectAttemptsReached(Exception):
    """Device could not reconnect after maximum attempts"""

    def __init__(self, last_error: Exception | type[Exception], attempts: int = 2):
        super().__init__(
            f"Could not connect to device after {attempts} unsuccessful attempts"
        )
        self.last_error = last_error
        self.attempts = attempts


class BaseAuthException(Exception):
    pass


class AuthFailedError(BaseAuthException):
    pass


class AuthErrors:
    BaseException = BaseAuthException

    class KeyInfoReqFailed(BaseAuthException):
        pass

    class NeedRefreshToken(BaseAuthException):
        pass

    class DeviceInternalError(BaseAuthException):
        pass

    class DeviceAlreadyBound(BaseAuthException):
        pass

    class NeedBindInstallFirst(BaseAuthException):
        pass

    class AppSendDataError(BaseAuthException):
        pass

    class WrongKey(BaseAuthException):
        pass

    class MaximumDevicesError(BaseAuthException):
        pass

    class UnknownError(BaseAuthException):
        pass

    _PAYLOAD_TO_ERROR = {
        b"\x00": None,
        b"\x01": NeedRefreshToken,
        b"\x02": DeviceInternalError,
        b"\x03": DeviceAlreadyBound,
        b"\x04": NeedBindInstallFirst,
        b"\x05": AppSendDataError,
        b"\x06": WrongKey,
        b"\x07": MaximumDevicesError,
    }

    @classmethod
    def from_payload(cls, payload: bytes) -> type[Exception] | None:
        return cls._PAYLOAD_TO_ERROR.get(payload, AuthErrors.UnknownError)


class UnsupportedBluetoothProtocol(Exception):
    def __init__(self, characteristic_type: str, available_characteristics: list[str]):
        characteristics = "\n    ".join(available_characteristics)
        super().__init__(
            f"Device is using unsupported protocol for {characteristic_type}.\n"
            f"Available characteristics:\n    {characteristics}"
        )

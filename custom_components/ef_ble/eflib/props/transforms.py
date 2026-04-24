from collections.abc import Callable


def out_power(x: float) -> float:
    """Negate and round output power, returning 0 for zero values"""
    return -round(x, 2) if x != 0 else 0.0


def flow_is_on(x: int) -> bool:
    """Return True when the flow info bitmask indicates an active port"""
    # Same check as in the app; values other than 0 (off) or 2 (on) are unknown
    return (int(x) & 0b11) in [0b10, 0b11]


def pround(precision: int = 2):
    """Return a transform that rounds a float to the given precision"""

    def _round(val: float | None) -> float | None:
        return None if val is None else round(val, precision)

    return _round


def pmultiply(x: int) -> Callable[[float | None], float | None]:
    """Return a transform that multiplies a float by x, preserving None"""

    def _multiply(value: float | None) -> float | None:
        return None if value is None else value * x

    return _multiply


def pdiv(
    divisor: float, precision: int | None = None
) -> Callable[[float | None], float | None]:
    """Return a transform that divides a float by divisor, optionally rounding"""

    def _divide(value: float | None) -> float | None:
        if value is None:
            return None
        result = value / divisor
        return round(result, precision) if precision is not None else result

    return _divide


def prop_has_bit_on(bit_position: int) -> Callable[[int | None], bool]:
    """Return a transform that checks whether a specific bit is set"""

    def transform(value: int | None) -> bool:
        if value is None:
            return False
        return bool((value >> bit_position) & 1)

    return transform


def prop_has_bit_off(bit_position: int) -> Callable[[int | None], bool]:
    """Return a transform that checks whether a specific bit is cleared"""

    def transform(value: int | None) -> bool:
        if value is None:
            return False
        return not bool((value >> bit_position) & 1)

    return transform

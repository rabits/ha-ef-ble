import functools
from collections.abc import Callable


def pround(precision: int = 2):
    def _round(val):
        return round(val, precision)

    return _round


class classproperty[T]:
    def __init__(self, method: Callable[..., T]):
        self.method = method
        functools.update_wrapper(self, method)

    def __get__(self, obj, cls=None) -> T:
        if cls is None:
            cls = type(obj)
        return self.method(cls)

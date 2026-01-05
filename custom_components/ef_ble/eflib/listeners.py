from collections.abc import Callable
from typing import TYPE_CHECKING


class ListenerGroup[T: Callable](list[T]):
    """Collection of listeners that can be called as a single listener"""

    if TYPE_CHECKING:
        # NOTE(gnox): ideally, this would be handled with ParamSpecs and in the runtime
        # __call__ method, but this does not work with listeners defined with 3.12 type
        # aliases so this is a workaround
        __call__: T
    else:

        def __call__(self, *args, **kwargs):
            for listener in self:
                listener(*args, **kwargs)

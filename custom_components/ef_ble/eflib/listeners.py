from collections.abc import Callable
from dataclasses import dataclass, field
from inspect import get_annotations
from typing import TYPE_CHECKING, Any, Self, dataclass_transform, overload


@dataclass_transform(kw_only_default=True)
class ListenerRegistry:
    """Registry for listeners"""

    def __init_subclass__(cls) -> None:
        for name in get_annotations(cls):
            setattr(cls, name, field(default_factory=ListenerGroup))

        dataclass(cls)

    @classmethod
    def create(cls):
        return cls._Descriptor[cls](cls)

    @dataclass
    class _Descriptor[T]:
        orig_cls: type

        def __set_name__(self, owner, name: str):
            self.private_name = (
                f"_{name}" if not hasattr(owner, f"_{name}") else f"__{name}"
            )

        @overload
        def __get__(self, instance: None, owner: type) -> T: ...

        @overload
        def __get__(self, instance: Any, owner: type) -> T: ...

        def __get__(self, instance: Any, owner: type) -> Self | T:
            if instance is None:
                return self

            cls = getattr(instance, self.private_name, None)
            if cls is None:
                cls = self.orig_cls()
                setattr(instance, self.private_name, cls)
            return cls


class ListenerGroup[T: Callable](list[T]):
    """Collection of listeners that can be called as a single listener"""

    def add(self, object: T) -> Callable[[], None]:
        self.append(object)

        def _unlisten():
            self.remove(object)

        return _unlisten

    if TYPE_CHECKING:
        # NOTE(gnox): ideally, this would be handled with ParamSpecs and in the runtime
        # __call__ method, but this does not work with listeners defined with 3.12 type
        # aliases so this is a workaround
        __call__: T
    else:

        def __call__(self, *args, **kwargs):
            for listener in self:
                listener(*args, **kwargs)

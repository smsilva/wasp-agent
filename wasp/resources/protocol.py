from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class ResourceProvider(Protocol):
    name: str

    def tools(self) -> list[Callable]: ...

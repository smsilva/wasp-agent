"""Channel registry and ChannelLoader.

Each channel package (telegram, discord, …) provides a :class:`Channel`
implementation and calls :func:`register` at package-import time. This mirrors
the side-effect import pattern already used by ``wasp/__init__.py`` to trigger
``wasp.telemetry.configure()``. Tests must call :func:`reset` between cases
to keep the registry deterministic; see ``tests/conftest.py``.
"""
from __future__ import annotations

from typing import AsyncContextManager, Iterable, Protocol

from wasp.clients import Notifier


class Channel(Protocol):
    name: str

    def enabled(self) -> bool: ...
    def build_interface(self, agent) -> object | None: ...
    def lifespan(self) -> AsyncContextManager | None: ...
    def notifier(self) -> Notifier | None: ...


_registry: dict[str, Channel] = {}


def register(channel: Channel) -> None:
    _registry[channel.name] = channel


def get(name: str) -> Channel | None:
    return _registry.get(name)


def iter_channels() -> Iterable[Channel]:
    return list(_registry.values())


def reset() -> None:
    _registry.clear()

"""Channel registry and ChannelLoader.

Each channel package (telegram, discord, …) provides a :class:`Channel`
implementation and calls :func:`register` at package-import time, guarded by
``if channels.get(NAME) is None`` so tests can pre-register fakes without
being clobbered by the side-effect import.

:func:`discover` walks ``wasp.clients`` and imports every subpackage so that
their ``__init__`` side-effects populate the registry without ``main.py``
having to know each channel name. Tests call :func:`reset` between cases
to keep the registry deterministic; see ``tests/conftest.py``.
"""

from __future__ import annotations

import importlib
import pkgutil
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, AsyncContextManager, Iterable, Protocol

if TYPE_CHECKING:
    from agno.os import AgentOS

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


def discover() -> None:
    """Import every subpackage under ``wasp.clients`` so their channel
    self-registration runs. Skips ``wasp.clients.channels`` itself and the
    ``local`` package, which has no ``Channel``.
    """
    import wasp.clients as pkg

    for info in pkgutil.iter_modules(pkg.__path__, prefix="wasp.clients."):
        if not info.ispkg or info.name == "wasp.clients.local":
            continue
        importlib.import_module(info.name)


class ChannelLoader:
    def __init__(self, agent) -> None:
        self._agent = agent

    def build_app(self) -> tuple[object, "AgentOS"]:
        from agno.os import AgentOS
        import wasp.telemetry as telemetry

        discover()
        active = [c for c in iter_channels() if c.enabled()]
        interfaces = [
            iface
            for c in active
            if (iface := c.build_interface(self._agent)) is not None
        ]
        agent_os = AgentOS(agents=[self._agent], interfaces=interfaces)
        app = agent_os.get_app()
        telemetry.register_prometheus_route(app)

        channel_cms = [cm for c in active if (cm := c.lifespan()) is not None]
        if channel_cms:
            original_lifespan = app.router.lifespan_context

            @asynccontextmanager
            async def composed_lifespan(app):
                async with AsyncExitStack() as stack:
                    for cm in channel_cms:
                        await stack.enter_async_context(cm)
                    async with original_lifespan(app):
                        yield

            app.router.lifespan_context = composed_lifespan

        return app, agent_os

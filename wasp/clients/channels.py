"""Channel registry and ChannelLoader.

Each channel package (telegram, discord, …) provides a :class:`Channel`
implementation and calls :func:`register` at package-import time. This mirrors
the side-effect import pattern already used by ``wasp/__init__.py`` to trigger
``wasp.telemetry.configure()``. Tests must call :func:`reset` between cases
to keep the registry deterministic; see ``tests/conftest.py``.
"""

from __future__ import annotations

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


class ChannelLoader:
    def __init__(self, agent) -> None:
        self._agent = agent

    def build_app(self) -> tuple[object, "AgentOS"]:
        from agno.os import AgentOS
        import wasp.telemetry as telemetry

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

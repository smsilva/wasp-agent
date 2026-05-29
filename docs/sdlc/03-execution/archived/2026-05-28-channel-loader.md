# Channel Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current `InterfaceLoader` + hardcoded `_select_notifier` branches with a per-channel `Channel` Protocol auto-registered into a global registry, so `main.py::create_app()` and `watcher.py` become channel-agnostic.

**Architecture:** Introduce `wasp/clients/channels.py` exposing a `Channel` Protocol, a process-global registry (`register/get/iter_channels/reset`) and a `ChannelLoader` that composes interfaces + lifespans into the FastAPI app. Each channel package (`telegram`, `discord`) gains a `channel.py` implementing the Protocol and registers itself on package import. `main.py` shrinks to four lines; `watcher._select_notifier` resolves channels by registry lookup. `wasp/clients/interfaces.py` and the `discord_pkg._notifier` module-level singleton are deleted.

**Tech Stack:** Python 3.14, agno (`AgentOS`, `Telegram` interface), FastAPI/Starlette lifespans (`contextlib.asynccontextmanager`), `discord.py`, pytest + ruff + uv.

**Spec:** `docs/sdlc/02-design/2026-05-28-channel-loader-design.md`

---

## File Structure

### New files

- `wasp/clients/channels.py` — `Channel` Protocol, registry primitives (`register`, `get`, `iter_channels`, `reset`), `ChannelLoader`.
- `wasp/clients/telegram/channel.py` — `TelegramChannel` implementing the Protocol.
- `wasp/clients/discord/channel.py` — `DiscordChannel` implementing the Protocol.
- `tests/test_channels.py` — unit tests for `Channel` Protocol, registry, `ChannelLoader`, and the two channel implementations.

### Modified files

- `wasp/clients/telegram/__init__.py` — re-export `TelegramChannel` and call `channels.register(TelegramChannel())`.
- `wasp/clients/discord/__init__.py` — re-export `DiscordChannel`, call `channels.register(DiscordChannel())`, remove `_notifier` module-level variable.
- `main.py::create_app()` — shrink to 4 lines (`ChannelLoader(agent).build_app()`).
- `wasp/watcher.py::_select_notifier` — registry-based resolution, remove `discord_pkg._notifier` import.
- `tests/conftest.py` — drop `wasp.clients.interfaces` from sys.modules cleanup, add `wasp.clients.channels`, `wasp.clients.telegram.channel`, `wasp.clients.discord.channel`; call `channels.reset()` after each test.
- `tests/test_main.py` — replace `InterfaceLoader.build_discord` patches with channel-loader-based patches.
- `tests/test_watcher.py` — rewrite the three `dc` notifier tests to register a fake channel via the registry.

### Deleted files

- `wasp/clients/interfaces.py`
- `tests/test_interface_loader.py`

---

## Conventions used throughout this plan

- Tests are written first; run them red, then green.
- Each task ends with `make format && make test` and a focused commit. The full `make e2e-with-debug` runs only at the very end.
- Commit messages follow Conventional Commits (`feat:`, `refactor:`, `test:`, `docs:`).
- Coverage must stay at 100% (`make test` runs `pytest --cov`).

---

## Task 1: Add `Channel` Protocol, registry, and `ChannelLoader` skeleton

**Files:**
- Create: `wasp/clients/channels.py`
- Test: `tests/test_channels.py`

- [ ] **Step 1: Write failing tests for the `Channel` Protocol shape and registry primitives**

```python
# tests/test_channels.py
import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def _reset_channels():
    from wasp.clients import channels
    channels.reset()
    yield
    channels.reset()


def test_register_and_get_returns_channel():
    from wasp.clients import channels

    ch = MagicMock(name="ch")
    ch.name = "fake"
    channels.register(ch)
    assert channels.get("fake") is ch


def test_get_returns_none_for_unknown_name():
    from wasp.clients import channels

    assert channels.get("missing") is None


def test_iter_channels_yields_registered_channels():
    from wasp.clients import channels

    a = MagicMock(); a.name = "a"
    b = MagicMock(); b.name = "b"
    channels.register(a)
    channels.register(b)
    assert set(channels.iter_channels()) == {a, b}


def test_register_overwrites_same_name():
    from wasp.clients import channels

    a = MagicMock(); a.name = "x"
    b = MagicMock(); b.name = "x"
    channels.register(a)
    channels.register(b)
    assert channels.get("x") is b
    assert list(channels.iter_channels()) == [b]


def test_reset_clears_registry():
    from wasp.clients import channels

    ch = MagicMock(); ch.name = "x"
    channels.register(ch)
    channels.reset()
    assert channels.get("x") is None
    assert list(channels.iter_channels()) == []
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_channels.py -v`
Expected: `ModuleNotFoundError: No module named 'wasp.clients.channels'` (collection-time failure for all five tests).

- [ ] **Step 3: Implement `Channel` Protocol, registry, and `reset()` in `wasp/clients/channels.py`**

```python
"""Channel registry and ChannelLoader.

Each channel package (telegram, discord, …) provides a :class:`Channel`
implementation and calls :func:`register` at package-import time. This mirrors
the side-effect import pattern already used by ``wasp/__init__.py`` to trigger
``wasp.telemetry.configure()``. Tests must call :func:`reset` between cases
to keep the registry deterministic; see ``tests/conftest.py``.
"""
from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_channels.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add wasp/clients/channels.py tests/test_channels.py
git commit -m "feat(channels): add Channel Protocol and global registry"
```

---

## Task 2: Add `ChannelLoader.build_app()`

**Files:**
- Modify: `wasp/clients/channels.py`
- Test: `tests/test_channels.py`

- [ ] **Step 1: Write failing tests for `ChannelLoader.build_app()`**

Append to `tests/test_channels.py`:

```python
def _fake_channel(name, *, enabled=True, interface=None, lifespan_cm=None, notifier=None):
    ch = MagicMock()
    ch.name = name
    ch.enabled = MagicMock(return_value=enabled)
    ch.build_interface = MagicMock(return_value=interface)
    ch.lifespan = MagicMock(return_value=lifespan_cm)
    ch.notifier = MagicMock(return_value=notifier)
    return ch


def test_build_app_collects_interfaces_from_enabled_channels(mock_agno):
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    iface_a = MagicMock(name="iface_a")
    iface_b = MagicMock(name="iface_b")
    channels.register(_fake_channel("a", interface=iface_a))
    channels.register(_fake_channel("b", interface=iface_b))
    channels.register(_fake_channel("c", enabled=False, interface=MagicMock()))

    agent = MagicMock()
    ChannelLoader(agent).build_app()

    agent_os_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert agent_os_kwargs["agents"] == [agent]
    assert set(agent_os_kwargs["interfaces"]) == {iface_a, iface_b}


def test_build_app_returns_app_and_agent_os(mock_agno):
    from wasp.clients.channels import ChannelLoader

    app, agent_os = ChannelLoader(MagicMock()).build_app()

    agent_os_mock = mock_agno["agno.os"].AgentOS.return_value
    assert app is agent_os_mock.get_app.return_value
    assert agent_os is agent_os_mock


def test_build_app_registers_prometheus_route(mock_agno, monkeypatch):
    import wasp.telemetry as telemetry
    from wasp.clients.channels import ChannelLoader

    spy = MagicMock()
    monkeypatch.setattr(telemetry, "register_prometheus_route", spy)

    app, _ = ChannelLoader(MagicMock()).build_app()
    spy.assert_called_once_with(app)


def test_build_app_skips_channels_with_none_interface(mock_agno):
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    channels.register(_fake_channel("no-iface", interface=None))
    ChannelLoader(MagicMock()).build_app()

    agent_os_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert agent_os_kwargs["interfaces"] == []


def test_build_app_ignores_disabled_channels(mock_agno):
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    disabled = _fake_channel("off", enabled=False, interface=MagicMock())
    channels.register(disabled)
    ChannelLoader(MagicMock()).build_app()

    disabled.build_interface.assert_not_called()
    agent_os_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert agent_os_kwargs["interfaces"] == []
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_channels.py -v`
Expected: 5 new tests fail with `ImportError: cannot import name 'ChannelLoader'`.

- [ ] **Step 3: Implement `ChannelLoader` (interfaces only — lifespan composition arrives in Task 3)**

Append to `wasp/clients/channels.py`:

```python
class ChannelLoader:
    def __init__(self, agent) -> None:
        self._agent = agent

    def build_app(self):
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
        return app, agent_os
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_channels.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add wasp/clients/channels.py tests/test_channels.py
git commit -m "feat(channels): add ChannelLoader.build_app for interface assembly"
```

---

## Task 3: Compose channel lifespans into the FastAPI app

**Files:**
- Modify: `wasp/clients/channels.py`
- Test: `tests/test_channels.py`

- [ ] **Step 1: Write failing tests for lifespan composition**

Append to `tests/test_channels.py`:

```python
async def test_build_app_wraps_lifespan_for_channels_that_provide_one(mock_agno):
    from contextlib import asynccontextmanager
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    enter_calls = []
    exit_calls = []

    @asynccontextmanager
    async def fake_channel_lifespan():
        enter_calls.append("ch")
        try:
            yield
        finally:
            exit_calls.append("ch")

    @asynccontextmanager
    async def original_lifespan(app):
        enter_calls.append("orig")
        try:
            yield
        finally:
            exit_calls.append("orig")

    channels.register(_fake_channel("dc", lifespan_cm=fake_channel_lifespan()))

    app, _ = ChannelLoader(MagicMock()).build_app()
    app.router.lifespan_context = original_lifespan

    # Re-invoke to trigger lifespan attachment after we replaced the original.
    # (ChannelLoader composed against the original AgentOS lifespan; this test
    # verifies the composition order is "channel CM wraps original".)
    async with app.router.lifespan_context(app):
        pass

    # Both should have been entered and exited; channel CM wraps original
    assert enter_calls == ["orig"] or enter_calls == ["ch", "orig"]
    # The above is permissive because order depends on composition; assert below
    # is the real contract:
    assert "ch" in enter_calls and "orig" in enter_calls
    assert "ch" in exit_calls and "orig" in exit_calls
```

Replace the test above (its commentary is wrong about reassigning lifespan after build) with this tighter version — overwrite the previous test in the same file:

```python
async def test_build_app_wraps_lifespan_for_channels_that_provide_one(mock_agno):
    from contextlib import asynccontextmanager
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    enter_calls: list[str] = []
    exit_calls: list[str] = []

    @asynccontextmanager
    async def fake_channel_lifespan():
        enter_calls.append("ch")
        try:
            yield
        finally:
            exit_calls.append("ch")

    @asynccontextmanager
    async def original_lifespan(app):
        enter_calls.append("orig")
        try:
            yield
        finally:
            exit_calls.append("orig")

    # Force AgentOS.get_app() to return an app whose router lifespan we control.
    fake_app = MagicMock()
    fake_app.router.lifespan_context = original_lifespan
    mock_agno["agno.os"].AgentOS.return_value.get_app.return_value = fake_app

    channels.register(_fake_channel("dc", lifespan_cm=fake_channel_lifespan()))
    app, _ = ChannelLoader(MagicMock()).build_app()

    async with app.router.lifespan_context(app):
        pass

    assert enter_calls == ["ch", "orig"]
    assert exit_calls == ["orig", "ch"]


async def test_build_app_does_not_wrap_lifespan_when_no_channel_provides_one(mock_agno):
    from contextlib import asynccontextmanager
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    @asynccontextmanager
    async def original_lifespan(app):
        yield

    fake_app = MagicMock()
    fake_app.router.lifespan_context = original_lifespan
    mock_agno["agno.os"].AgentOS.return_value.get_app.return_value = fake_app

    channels.register(_fake_channel("tg", lifespan_cm=None))
    app, _ = ChannelLoader(MagicMock()).build_app()

    assert app.router.lifespan_context is original_lifespan


async def test_build_app_chains_multiple_channel_lifespans(mock_agno):
    from contextlib import asynccontextmanager
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    enter_calls: list[str] = []
    exit_calls: list[str] = []

    def make_cm(label):
        @asynccontextmanager
        async def cm():
            enter_calls.append(label)
            try:
                yield
            finally:
                exit_calls.append(label)
        return cm()

    @asynccontextmanager
    async def original_lifespan(app):
        enter_calls.append("orig")
        try:
            yield
        finally:
            exit_calls.append("orig")

    fake_app = MagicMock()
    fake_app.router.lifespan_context = original_lifespan
    mock_agno["agno.os"].AgentOS.return_value.get_app.return_value = fake_app

    channels.register(_fake_channel("a", lifespan_cm=make_cm("a")))
    channels.register(_fake_channel("b", lifespan_cm=make_cm("b")))
    app, _ = ChannelLoader(MagicMock()).build_app()

    async with app.router.lifespan_context(app):
        pass

    # Both channel CMs must enter before the original and exit after it.
    assert enter_calls[-1] == "orig"
    assert exit_calls[0] == "orig"
    assert set(enter_calls[:-1]) == {"a", "b"}
    assert set(exit_calls[1:]) == {"a", "b"}
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_channels.py -v`
Expected: the three new lifespan tests fail because `ChannelLoader.build_app` does not yet compose lifespans.

- [ ] **Step 3: Implement lifespan composition**

Replace the `build_app` method body in `wasp/clients/channels.py` with:

```python
    def build_app(self):
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_channels.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add wasp/clients/channels.py tests/test_channels.py
git commit -m "feat(channels): compose channel lifespans into FastAPI app"
```

---

## Task 4: Wire `channels.reset()` into the test fixture

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing test that asserts state does not leak between tests**

Append to `tests/test_channels.py`:

```python
def test_registry_is_clean_at_test_start_a():
    from wasp.clients import channels
    from unittest.mock import MagicMock

    assert list(channels.iter_channels()) == []
    ch = MagicMock(); ch.name = "leak"
    channels.register(ch)


def test_registry_is_clean_at_test_start_b():
    from wasp.clients import channels

    # If the previous test leaked, this assertion fails.
    assert list(channels.iter_channels()) == []
```

- [ ] **Step 2: Run tests, verify the leak-detection test fails when the per-file `_reset_channels` fixture is removed**

Temporarily comment out the `@pytest.fixture(autouse=True)` on `_reset_channels` at the top of `tests/test_channels.py`, then:

Run: `uv run pytest tests/test_channels.py::test_registry_is_clean_at_test_start_b -v`
Expected: the test fails with the leaked `"leak"` channel still present (assuming `_a` ran first; if pytest order differs in your environment, run both with `--tb=short` and confirm at least one ordering produces the leak).

Restore the `@pytest.fixture(autouse=True)` decorator.

- [ ] **Step 3: Move the reset into the global `mock_agno` fixture so every test gets it**

In `tests/conftest.py`, add `wasp.clients.channels`, `wasp.clients.telegram.channel`, `wasp.clients.discord.channel` to BOTH `sys.modules.pop` loops (pre-yield and post-yield), and immediately after the `monkeypatch.setattr("dotenv.load_dotenv", ...)` line, add:

```python
    # Channel registry is process-global; clear it so each test starts empty.
    from wasp.clients import channels as _channels
    _channels.reset()
```

Also append `_channels.reset()` to the cleanup block after `yield mocks`:

```python
    from wasp.clients import channels as _channels
    _channels.reset()
```

Then DELETE the per-file `_reset_channels` autouse fixture at the top of `tests/test_channels.py` (the global one now covers it).

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/test_channels.py -v`
Expected: 15 passed, no leaks.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_channels.py
git commit -m "test(channels): reset registry between tests"
```

---

## Task 5: Add `TelegramChannel`

**Files:**
- Create: `wasp/clients/telegram/channel.py`
- Modify: `wasp/clients/telegram/__init__.py`
- Test: `tests/test_channels.py`

- [ ] **Step 1: Write failing tests for `TelegramChannel`**

Append to `tests/test_channels.py`:

```python
def test_telegram_channel_name_is_tg():
    from wasp.clients.telegram.channel import TelegramChannel

    assert TelegramChannel().name == "tg"


def test_telegram_channel_enabled_when_token_set(monkeypatch):
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-123")
    assert TelegramChannel().enabled() is True


def test_telegram_channel_disabled_when_no_token(monkeypatch):
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    assert TelegramChannel().enabled() is False


def test_telegram_channel_build_interface_constructs_and_wraps(mock_agno, monkeypatch):
    from unittest.mock import patch
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-xyz")
    agent = MagicMock()
    with patch("wasp.clients.telegram.channel._install_start_token_handler") as install:
        iface = TelegramChannel().build_interface(agent)

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_called_once_with(
        agent=agent, token="tok-xyz"
    )
    install.assert_called_once_with(iface)


def test_telegram_channel_build_interface_returns_none_without_token(mock_agno, monkeypatch):
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    assert TelegramChannel().build_interface(MagicMock()) is None
    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()


def test_telegram_channel_lifespan_is_none():
    from wasp.clients.telegram.channel import TelegramChannel

    assert TelegramChannel().lifespan() is None


def test_telegram_channel_notifier_returns_telegram_notifier(monkeypatch):
    from wasp.clients.telegram.channel import TelegramChannel
    from wasp.clients.telegram import TelegramNotifier

    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-1")
    notifier = TelegramChannel().notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_telegram_channel_notifier_returns_none_without_token(monkeypatch):
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    assert TelegramChannel().notifier() is None


def test_importing_telegram_package_registers_channel(monkeypatch):
    from wasp.clients import channels

    assert channels.get("tg") is None
    import wasp.clients.telegram  # noqa: F401
    ch = channels.get("tg")
    assert ch is not None
    assert ch.name == "tg"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_channels.py -v -k telegram`
Expected: all telegram tests fail with `ModuleNotFoundError: No module named 'wasp.clients.telegram.channel'` or `channels.get("tg") is None` for the registration test.

- [ ] **Step 3: Create `wasp/clients/telegram/channel.py`**

```python
import os
from contextlib import AbstractAsyncContextManager

from wasp.clients import Notifier
from wasp.clients.telegram.notifier import TelegramNotifier
from wasp.clients.telegram.webhook import _install_start_token_handler


class TelegramChannel:
    name = "tg"

    def enabled(self) -> bool:
        return bool(os.getenv("TELEGRAM_TOKEN"))

    def build_interface(self, agent):
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            return None
        from agno.os.interfaces.telegram import Telegram

        iface = Telegram(agent=agent, token=token)
        _install_start_token_handler(iface)
        return iface

    def lifespan(self) -> AbstractAsyncContextManager | None:
        return None

    def notifier(self) -> Notifier | None:
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            return None
        return TelegramNotifier(token=token)
```

- [ ] **Step 4: Register the channel from the package `__init__.py`**

Edit `wasp/clients/telegram/__init__.py` to:

```python
from wasp.clients import channels
from wasp.clients.telegram.channel import TelegramChannel as TelegramChannel
from wasp.clients.telegram.notifier import TelegramNotifier as TelegramNotifier
from wasp.clients.telegram.webhook import (
    _install_start_token_handler as _install_start_token_handler,
)
from wasp.clients.telegram.webhook import _process_start_token as _process_start_token

channels.register(TelegramChannel())
```

- [ ] **Step 5: Run telegram-channel tests, verify they pass**

Run: `uv run pytest tests/test_channels.py -v -k telegram`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add wasp/clients/telegram/channel.py wasp/clients/telegram/__init__.py tests/test_channels.py
git commit -m "feat(telegram): add TelegramChannel and self-registration"
```

---

## Task 6: Add `DiscordChannel`

**Files:**
- Create: `wasp/clients/discord/channel.py`
- Modify: `wasp/clients/discord/__init__.py` (delete `_notifier` module-level variable)
- Test: `tests/test_channels.py`

- [ ] **Step 1: Write failing tests for `DiscordChannel`**

Append to `tests/test_channels.py`:

```python
def test_discord_channel_name_is_dc():
    from wasp.clients.discord.channel import DiscordChannel

    assert DiscordChannel().name == "dc"


def test_discord_channel_enabled_when_token_set(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")
    assert DiscordChannel().enabled() is True


def test_discord_channel_disabled_when_no_token(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)
    assert DiscordChannel().enabled() is False


def test_discord_channel_build_interface_returns_none(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")
    assert DiscordChannel().build_interface(MagicMock()) is None


def test_discord_channel_notifier_returns_same_instance_twice(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel
    from wasp.clients.discord.notifier import DiscordNotifier

    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")
    ch = DiscordChannel()
    n1 = ch.notifier()
    n2 = ch.notifier()
    assert isinstance(n1, DiscordNotifier)
    assert n1 is n2


def test_discord_channel_notifier_returns_none_without_token(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)
    assert DiscordChannel().notifier() is None


async def test_discord_channel_lifespan_starts_and_stops_bot(monkeypatch, mock_agno):
    import asyncio
    from unittest.mock import AsyncMock, patch
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")

    fake_bot = MagicMock()
    fake_bot.start_background = AsyncMock()
    fake_bot.close = AsyncMock()

    with patch("wasp.clients.discord.channel.DiscordBot", return_value=fake_bot):
        ch = DiscordChannel()
        ch._agent = MagicMock()  # set by build_interface in real flow; bypass here
        cm = ch.lifespan()
        assert cm is not None

        async with cm:
            await asyncio.sleep(0)

    fake_bot.close.assert_awaited_once()


def test_discord_channel_lifespan_is_none_without_token(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)
    assert DiscordChannel().lifespan() is None


def test_importing_discord_package_registers_channel(monkeypatch):
    from wasp.clients import channels

    assert channels.get("dc") is None
    import wasp.clients.discord  # noqa: F401
    ch = channels.get("dc")
    assert ch is not None
    assert ch.name == "dc"


def test_discord_package_no_longer_exposes_notifier_singleton():
    import wasp.clients.discord as dc_pkg

    assert not hasattr(dc_pkg, "_notifier")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_channels.py -v -k discord`
Expected: discord tests fail with `ModuleNotFoundError: No module named 'wasp.clients.discord.channel'`.

- [ ] **Step 3: Create `wasp/clients/discord/channel.py`**

Note the design subtlety: `DiscordChannel` must own both the `DiscordNotifier` (returned from `notifier()`) and the `DiscordBot` (started inside `lifespan()`); both must share the same notifier instance so the bot wires `set_loop()` on the same object the watcher will reach via `notifier()`. We also need the agent for the bot — the bot is built lazily inside `lifespan()`, so we add an `_agent` slot that `ChannelLoader` will populate. To keep `ChannelLoader` channel-agnostic we make `lifespan()` accept no args (Protocol contract) but `DiscordChannel` carries the agent via a `set_agent()` setter call we'll add to `Channel` Protocol semantics. Simpler approach: pass the agent through `build_interface(agent)` and stash it.

Adjust the implementation to stash the agent during `build_interface`:

```python
import os
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from wasp.clients import Notifier
from wasp.clients.discord.bot import DiscordBot
from wasp.clients.discord.notifier import DiscordNotifier


class DiscordChannel:
    name = "dc"

    def __init__(self) -> None:
        self._agent = None
        self._notifier: DiscordNotifier | None = None

    def enabled(self) -> bool:
        return bool(os.getenv("DISCORD_APP_TOKEN"))

    def build_interface(self, agent):
        # Discord is not an agno Interface — capture the agent for lifespan().
        self._agent = agent
        return None

    def lifespan(self) -> AbstractAsyncContextManager | None:
        if not self.enabled():
            return None

        notifier = self.notifier()
        bot = DiscordBot(agent=self._agent, notifier=notifier)

        @asynccontextmanager
        async def discord_lifespan():
            import asyncio

            task = asyncio.ensure_future(bot.start_background())
            try:
                yield
            finally:
                task.cancel()
                await bot.close()

        return discord_lifespan()

    def notifier(self) -> Notifier | None:
        if not os.getenv("DISCORD_APP_TOKEN"):
            return None
        if self._notifier is None:
            self._notifier = DiscordNotifier()
        return self._notifier
```

- [ ] **Step 4: Strip `_notifier` from `wasp/clients/discord/__init__.py`**

Replace `wasp/clients/discord/__init__.py` with:

```python
from wasp.clients import channels
from wasp.clients.discord.bot import DiscordBot as DiscordBot
from wasp.clients.discord.channel import DiscordChannel as DiscordChannel
from wasp.clients.discord.notifier import DiscordNotifier as DiscordNotifier

channels.register(DiscordChannel())
```

- [ ] **Step 5: Run discord-channel tests, verify they pass**

Run: `uv run pytest tests/test_channels.py -v -k discord`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add wasp/clients/discord/channel.py wasp/clients/discord/__init__.py tests/test_channels.py
git commit -m "feat(discord): add DiscordChannel and drop module-level notifier"
```

---

## Task 7: Refactor `_select_notifier` to use the registry

**Files:**
- Modify: `wasp/watcher.py`
- Modify: `tests/test_watcher.py`

- [ ] **Step 1: Rewrite the existing `dc`-channel tests in `tests/test_watcher.py` to use the registry**

In `tests/test_watcher.py`, REPLACE the three Discord tests
(`test_select_notifier_dc_channel_picks_discord_notifier`,
`test_select_notifier_dc_channel_returns_none_when_no_singleton`,
`test_select_notifier_discord_kind_returns_singleton`) with:

```python
def test_select_notifier_dc_channel_uses_registered_channel(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.clients import channels
    from wasp.watcher import _select_notifier

    fake_notifier = MagicMock()
    fake_channel = MagicMock()
    fake_channel.name = "dc"
    fake_channel.notifier = MagicMock(return_value=fake_notifier)
    channels.register(fake_channel)

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    assert _select_notifier(channel="dc") is fake_notifier


def test_select_notifier_dc_channel_returns_none_when_unregistered(monkeypatch):
    from wasp.watcher import _select_notifier

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    assert _select_notifier(channel="dc") is None


def test_select_notifier_env_kind_resolves_via_registry(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.clients import channels
    from wasp.watcher import _select_notifier

    fake_notifier = MagicMock()
    fake_channel = MagicMock()
    fake_channel.name = "dc"
    fake_channel.notifier = MagicMock(return_value=fake_notifier)
    channels.register(fake_channel)

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "dc")
    assert _select_notifier() is fake_notifier
```

ALSO, the existing test `test_select_notifier_telegram_when_env_explicit` uses `WASP_AGENT_NOTIFIER=telegram`. With the new design, the kind string is the channel name (`tg`), not `telegram`. UPDATE that test plus the two other tests that hardcode `telegram` / `discord` kinds:

In `test_select_notifier_telegram_when_env_explicit`:

```python
    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "tg")
```

In `test_select_notifier_returns_none_when_telegram_without_token`:

```python
    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "tg")
```

Both of those tests also need the Telegram channel registered (the test fixture's `mock_agno` resets the registry to empty). Add at the top of each test body:

```python
    import wasp.clients.telegram  # noqa: F401 — triggers channel registration
```

- [ ] **Step 2: Run watcher tests, verify the rewritten ones fail**

Run: `uv run pytest tests/test_watcher.py -v -k select_notifier`
Expected: the three rewritten `dc` tests fail because `_select_notifier` still reads `discord_pkg._notifier`; the updated telegram tests may also fail for the same reason.

- [ ] **Step 3: Rewrite `_select_notifier` in `wasp/watcher.py`**

In `wasp/watcher.py`:

- Remove the import `import wasp.clients.discord as discord_pkg` at the top.
- Add: `from wasp.clients import channels`.
- Replace the entire `_select_notifier` function with:

```python
def _select_notifier(channel: str | None = None) -> Notifier | None:
    kind = os.getenv("WASP_AGENT_NOTIFIER")
    if kind == "console" or (kind is None and channel == "local"):
        return ConsoleNotifier()
    target = kind or channel
    if target is None:
        token = os.getenv("TELEGRAM_TOKEN")
        return TelegramNotifier(token=token) if token else ConsoleNotifier()
    registered = channels.get(target)
    return registered.notifier() if registered else None
```

- [ ] **Step 4: Run all watcher tests**

Run: `uv run pytest tests/test_watcher.py -v`
Expected: all watcher tests pass.

- [ ] **Step 5: Commit**

```bash
git add wasp/watcher.py tests/test_watcher.py
git commit -m "refactor(watcher): resolve notifiers via channel registry"
```

---

## Task 8: Shrink `main.py::create_app()` and delete `InterfaceLoader`

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`
- Modify: `tests/conftest.py` (drop `wasp.clients.interfaces` from sys.modules cleanup)
- Delete: `wasp/clients/interfaces.py`
- Delete: `tests/test_interface_loader.py`

- [ ] **Step 1: Update `tests/test_main.py` to assert the new shape**

Replace the entire contents of `tests/test_main.py` with:

```python
def test_agent_os_with_telegram_token(mock_agno, monkeypatch):
    """AgentOS receives the agent and Telegram interface when TELEGRAM_TOKEN is set."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-token-123")

    import main  # noqa: F401

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_called_once_with(
        agent=mock_agno["agno.agent"].Agent.return_value,
        token="test-token-123",
    )
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert len(call_kwargs["interfaces"]) == 1


def test_telegram_not_added_without_token(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    import main  # noqa: F401

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert call_kwargs["interfaces"] == []


def test_prometheus_route_registered(mock_agno, monkeypatch):
    from unittest.mock import MagicMock
    import wasp.telemetry as telemetry

    spy = MagicMock()
    monkeypatch.setattr(telemetry, "register_prometheus_route", spy)

    import main

    spy.assert_called_once_with(main.app)


def test_main_initializes_auth_db(mock_agno, monkeypatch):
    init_called = []
    monkeypatch.setattr(
        "wasp.auth.init_db", lambda db_file=None: init_called.append(db_file)
    )
    import main  # noqa: F401

    assert init_called


def test_install_start_token_handler_called_with_token(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tk")

    import main  # noqa: F401

    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    interface = call_kwargs["interfaces"][0]
    assert callable(interface.get_router)


def test_startup_called_on_import(mock_agno, monkeypatch):
    from unittest.mock import MagicMock
    import wasp.startup as _startup

    spy = MagicMock()
    monkeypatch.setattr(_startup, "startup", spy)

    import main  # noqa: F401

    spy.assert_called_once()


def test_discord_lifespan_wraps_app_when_token_set(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")

    import main

    # ChannelLoader composed a channel lifespan on top of the original AgentOS one.
    lifespan_name = getattr(main.app.router.lifespan_context, "__name__", "")
    assert lifespan_name == "composed_lifespan"


def test_no_discord_lifespan_wrap_without_token(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)

    import main

    lifespan_name = getattr(main.app.router.lifespan_context, "__name__", "")
    assert lifespan_name != "composed_lifespan"


def test_create_app_returns_app_and_agent_os(mock_agno, monkeypatch):
    import main

    assert main.app is not None
    assert main.agent_os is mock_agno["agno.os"].AgentOS.return_value
```

- [ ] **Step 2: Rewrite `main.py`**

Replace lines 16–52 of `main.py` (everything after `startup()`) with:

```python
import wasp.telemetry as telemetry  # noqa: E402 F401
from wasp import auth  # noqa: E402
from wasp.agent import build_agent  # noqa: E402
from wasp.clients.channels import ChannelLoader  # noqa: E402
import wasp.clients.telegram  # noqa: E402 F401 — registers TelegramChannel
import wasp.clients.discord  # noqa: E402 F401 — registers DiscordChannel


def create_app():
    auth.init_db()
    agent = build_agent()
    return ChannelLoader(agent).build_app()


app, agent_os = create_app()


if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)
```

The `import wasp.telemetry` line stays (its `# noqa: F401` is new — it's no longer used directly here, but importing it preserves the existing telemetry init side effects that downstream tests check; if `make test` shows the import is genuinely unused, drop the line and the `F401`).

- [ ] **Step 3: Delete `wasp/clients/interfaces.py` and `tests/test_interface_loader.py`**

```bash
rm wasp/clients/interfaces.py tests/test_interface_loader.py
```

- [ ] **Step 4: Drop `wasp.clients.interfaces` from `tests/conftest.py`**

In `tests/conftest.py`, remove the two occurrences of `"wasp.clients.interfaces",` from the `sys.modules.pop` loops (pre-yield and post-yield).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests pass (261 baseline + new channels tests − 7 interface_loader tests deleted).

- [ ] **Step 6: Run lint and format**

```bash
make format
ruff check .
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_main.py tests/conftest.py
git rm wasp/clients/interfaces.py tests/test_interface_loader.py
git commit -m "refactor(main): shrink create_app via ChannelLoader and drop InterfaceLoader"
```

---

## Task 9: Verify coverage and run e2e

**Files:** none (verification only)

- [ ] **Step 1: Run coverage report**

Run: `uv run pytest --cov`
Expected: total coverage = 100%. If a line is uncovered, add a targeted test before continuing.

- [ ] **Step 2: Run e2e suite**

Run: `make e2e-with-debug`
Expected: pass.

- [ ] **Step 3: Smoke check the new channel surface**

Read the resulting `wasp/clients/channels.py`, `telegram/channel.py`, `discord/channel.py` and confirm the success criterion from the spec: adding a hypothetical `google_chat` channel would mean creating `wasp/clients/google_chat/{__init__.py, channel.py}` and adding one `import wasp.clients.google_chat` line in `main.py`. Nothing in `ChannelLoader` or `watcher.py` should need to change. If anything in the implementation forces a central edit, fix it and re-run Step 1.

- [ ] **Step 4: Commit any verification fixes**

If Step 3 surfaced an issue and you patched it, commit with a focused message (`fix(channels): …`). Otherwise no commit.

---

## Task 10: Mark spec as Implemented and clean up HANDOFF.md

**Files:**
- Modify: `docs/sdlc/02-design/2026-05-28-channel-loader-design.md`
- Move: `docs/sdlc/02-design/2026-05-28-channel-loader-design.md` → `docs/sdlc/02-design/archived/`
- Move: `docs/sdlc/03-execution/2026-05-28-channel-loader.md` → `docs/sdlc/03-execution/archived/`
- Modify: `HANDOFF.md`

- [ ] **Step 1: Flip spec status to Implemented**

Open `docs/sdlc/02-design/2026-05-28-channel-loader-design.md` and change line 3 from:

```
**Status:** Approved
```

to:

```
**Status:** Implemented
```

- [ ] **Step 2: Archive spec + plan**

```bash
mkdir -p docs/sdlc/02-design/archived docs/sdlc/03-execution/archived
git mv docs/sdlc/02-design/2026-05-28-channel-loader-design.md docs/sdlc/02-design/archived/
git mv docs/sdlc/03-execution/2026-05-28-channel-loader.md docs/sdlc/03-execution/archived/
```

- [ ] **Step 3: Rewrite `HANDOFF.md` to drop the completed initiative**

Update `HANDOFF.md`:
- Delete the entire "Why" and "In Progress" sections about the channel loader.
- Move the channel-loader spec/plan into the "Implementados (aguardando marcação após merge)" list.
- Replace "How to Resume" and "Next Steps" with a short pointer to pick the next backlog item (Discord slash commands, LLM eval, OTEL tracing — pick whichever the user signals).

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md docs/sdlc/
git commit -m "docs(sdlc): archive channel loader spec and plan"
```

---

## Self-Review checklist (executed before handoff)

**Spec coverage**

| Spec section | Implemented in |
|---|---|
| `Channel` Protocol | Task 1 |
| Global registry (`register/get/iter_channels/reset`) | Task 1 |
| `ChannelLoader` — interface assembly | Task 2 |
| `ChannelLoader` — lifespan composition | Task 3 |
| Test-registry reset between tests | Task 4 |
| `TelegramChannel` + self-registration | Task 5 |
| `DiscordChannel` + self-registration + dropped `_notifier` singleton | Task 6 |
| `_select_notifier` registry-based + `local` fallback + `TELEGRAM_TOKEN` default | Task 7 |
| `main.py::create_app()` ≤5 lines | Task 8 |
| Delete `wasp/clients/interfaces.py` | Task 8 |
| `make format` / `make test` / `make e2e-with-debug` green, 100% cov | Task 9 |
| Spec marked `Implemented`, HANDOFF.md updated | Task 10 |

**Placeholder scan:** no "TBD", "TODO", "implement later", or vague "handle edge cases" steps. Every code step contains actual code. Every test step contains the assertion bodies.

**Type / name consistency:** `Channel.name`, `enabled()`, `build_interface(agent)`, `lifespan()`, `notifier()` are spelled identically across the Protocol, `TelegramChannel`, `DiscordChannel`, the registry tests, and `_select_notifier`. The composed lifespan is named `composed_lifespan` consistently across the implementation and the assertions in `tests/test_main.py`.

**Known divergence from spec:** the spec sketches the new `_select_notifier` with `if kind == "console" or channel == "local"` as a single branch. Task 7 splits it slightly (`kind == "console" or (kind is None and channel == "local")`) so an explicit `WASP_AGENT_NOTIFIER=tg` keeps overriding `channel == "local"` per the existing `test_select_notifier_env_overrides_channel` test. Behaviour matches the spec's intent; the literal expression differs.
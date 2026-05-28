# Channel loader — design

**Status:** Approved
**Date:** 2026-05-28
**Scope:** `main.py`, `wasp/clients/interfaces.py`, `wasp/watcher.py`, `wasp/clients/telegram/`, `wasp/clients/discord/`

## Problem

Channel-specific bootstrap leaks into three places:

1. **`main.py::create_app()`** assembles the Discord lifespan inline (captures `app.router.lifespan_context`, schedules `start_background()`, registers `close()`).
2. **`InterfaceLoader`** exposes asymmetric APIs (`build()` for agno interfaces, `build_discord()` for the Discord bot) and writes a module-level singleton `wasp.clients.discord._notifier` so the watcher can find it.
3. **`watcher._select_notifier`** hard-codes `if kind == "telegram"`, `if kind == "discord"`, and reads `discord_pkg._notifier` directly.

Adding Google Chat or any future channel currently requires editing all three sites.

## Goal

Each channel owns its own bootstrap. `main.py` knows only one object — the `ChannelLoader` — and adding a new channel means creating one package, not editing central code.

### Success criteria

1. `main.py::create_app()` fits in ≤5 lines, no `if`/lifespan inline.
2. Adding a hypothetical `google_chat` channel: create `wasp/clients/google_chat/{__init__.py, channel.py}` and import it. **Zero** changes to `main.py`, `ChannelLoader`, or `watcher.py`.
3. `make format`, `make test`, `make e2e-with-debug` pass.
4. Coverage stays at 100%.

### Non-goals

- Do **not** rewrite `wasp/clients/telegram/webhook.py` or `wasp/clients/discord/bot.py`.
- Do **not** unify Telegram (agno `Interface`) and Discord (own bot) into a single transport — they stay distinct; `Channel` adapts both.
- Do **not** touch `wasp/auth.py`, `wasp/agent.py`, or telemetry internals.

## Design

### Components

#### `wasp/clients/channels.py` (new)

Heart of the abstraction. Contains:

- **`Channel` Protocol:**
  ```python
  class Channel(Protocol):
      name: str
      def enabled(self) -> bool: ...
      def build_interface(self, agent) -> Interface | None: ...
      def lifespan(self) -> AsyncContextManager | None: ...
      def notifier(self) -> Notifier | None: ...
  ```
- **Global registry:** `register(channel)`, `get(name) -> Channel | None`, `iter_channels()`, `reset()` (test hook).
- **`ChannelLoader`:** orchestrates assembly — iterates enabled channels, builds `AgentOS`, composes lifespans, attaches telemetry, returns `(app, agent_os)`.

#### `wasp/clients/telegram/channel.py` (new)

`TelegramChannel` implements `Channel`:

- `name = "tg"`
- `enabled()` → `bool(os.getenv("TELEGRAM_TOKEN"))`
- `build_interface(agent)` → constructs `Telegram(agent=agent, token=...)`, calls `_install_start_token_handler(iface)`, returns it
- `lifespan()` → `None`
- `notifier()` → `TelegramNotifier(token=...)`

Registration: `wasp/clients/telegram/__init__.py` instantiates and calls `channels.register(...)` at import time.

#### `wasp/clients/discord/channel.py` (new)

`DiscordChannel` implements `Channel`:

- `name = "dc"`
- `enabled()` → `bool(os.getenv("DISCORD_APP_TOKEN"))`
- `build_interface(agent)` → `None` (Discord is not an agno `Interface`)
- `lifespan()` → `@asynccontextmanager` that schedules `start_background()` and ensures `close()` on exit — the block currently inlined in `main.py::create_app()`
- `notifier()` → single `DiscordNotifier` shared with the bot

Registration: `wasp/clients/discord/__init__.py` instantiates and calls `channels.register(...)` at import time. The `_notifier` module-level variable is **removed**.

#### `main.py::create_app()` (refactor)

```python
def create_app():
    auth.init_db()
    agent = build_agent()
    channel_loader = ChannelLoader(agent)
    return channel_loader.build_app()
```

#### `wasp/watcher.py::_select_notifier` (refactor)

```python
def _select_notifier(channel: str | None = None) -> Notifier | None:
    kind = os.getenv("WASP_AGENT_NOTIFIER")
    if kind == "console" or channel == "local":
        return ConsoleNotifier()
    target = kind or channel
    if target is None:
        return TelegramNotifier(token=os.getenv("TELEGRAM_TOKEN")) if os.getenv("TELEGRAM_TOKEN") else ConsoleNotifier()
    registered = channels.get(target)
    return registered.notifier() if registered else None
```

No more `discord_pkg._notifier` reads. No more `if kind == "discord"` branches.

#### `wasp/clients/interfaces.py`

Deleted. `InterfaceLoader` is replaced by `ChannelLoader`.

### Startup flow

1. `main.py` imports `wasp.clients.telegram` and `wasp.clients.discord`. Each package's `__init__.py` registers its `Channel` instance.
2. `ChannelLoader(agent).build_app()`:
   a. Filters channels where `enabled()` is true.
   b. Collects non-`None` results of `build_interface(agent)` → passes to `AgentOS(agents=[agent], interfaces=[...])`.
   c. `app = agent_os.get_app()`.
   d. `telemetry.register_prometheus_route(app)`.
   e. For each enabled channel with `lifespan() is not None`, composes it with `app.router.lifespan_context` (chained `asynccontextmanager`).
   f. Returns `(app, agent_os)`.

### Notifier resolution flow

1. `watch_platform` calls `_select_notifier(channel)` with the parsed channel prefix (`tg`, `dc`, `local`).
2. `_select_notifier` honours `WASP_AGENT_NOTIFIER` override, then `local` short-circuit, then queries `channels.get(channel).notifier()`.
3. Returns `None` if no match — caller logs and skips.

### `local` channel

`ConsoleNotifier` stays in `wasp/clients/local/`. It does **not** become a `Channel` (no interface, no lifespan, no env-driven enablement). It is resolved by the explicit fallback in `_select_notifier`.

## Testability

- `wasp/clients/channels.py` exposes `reset()`. `tests/conftest.py` calls it between tests to guarantee isolation.
- Each `Channel` is unit-testable with mocked envs.
- `ChannelLoader.build_app()` is tested with fake `Channel` instances registered explicitly — no real Telegram/Discord setup needed.
- `watcher._select_notifier` tests register fake channels via `channels.register(FakeChannel("tg"))` and assert the resolver.
- `make e2e-with-debug` covers the real flow by importing `main.py`.

## Lint / style notes

- Re-exports in `__init__.py` need explicit alias to avoid ruff F401: `from wasp.clients.telegram.channel import TelegramChannel as TelegramChannel`.
- Import-time side effects (`channels.register(...)`) are acceptable here — they mirror how `wasp.telemetry.configure()` is triggered by `wasp/__init__.py`. Document in `wasp/clients/channels.py` docstring.

## Out of scope (deferred)

- Hot-reload of channels at runtime.
- Multi-instance notifiers (multiple Discord guilds, multiple Telegram bots).
- Configuration-file-driven channel selection (today envs are sufficient).
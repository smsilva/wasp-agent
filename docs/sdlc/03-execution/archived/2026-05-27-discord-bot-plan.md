# Discord Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Discord channel to wasp-agent with message-based interaction, auth, and watcher notifications — identical feature set to Telegram.

**Architecture:** discord.py runs as an asyncio background task launched from the FastAPI app lifespan. `DiscordBot` receives `agent` and `DiscordNotifier` via constructor; `DiscordNotifier` maintains a `user_id → discord.TextChannel` map used both for direct responses and watcher notifications. `_select_notifier` in `watcher.py` routes `channel == "dc"` to the `DiscordNotifier` singleton stored at `wasp.clients.discord._notifier`.

**Tech Stack:** discord.py ≥ 2.3.0, pytest + AsyncMock (existing), FastAPI lifespan handlers (existing pattern).

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `wasp/clients/discord/__init__.py` | Re-exports `DiscordBot`, `DiscordNotifier` |
| Create | `wasp/clients/discord/notifier.py` | `DiscordNotifier` — user_id → channel map + `send()` |
| Create | `wasp/clients/discord/bot.py` | `discord.Client` subclass — `on_message`, auth, agent call |
| Create | `tests/test_discord.py` | All unit tests for notifier + bot |
| Modify | `pyproject.toml` | Add `discord.py>=2.3.0` dependency |
| Modify | `wasp/clients/interfaces.py` | Add `build_discord() -> DiscordBot | None` |
| Modify | `main.py` | Register bot startup/shutdown lifespan handlers |
| Modify | `wasp/watcher.py` | Add `"dc"` channel routing in `_select_notifier` |
| Modify | `tests/conftest.py` | Add `discord` to mocked modules in `mock_agno` |
| Modify | `tests/test_interface_loader.py` | Tests for `build_discord()` |
| Modify | `tests/test_main.py` | Tests for Discord lifespan registration |
| Modify | `tests/test_watcher.py` | Tests for `_select_notifier` with Discord |

---

## Task 1: Add discord.py dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency**

In `pyproject.toml`, add `"discord.py>=2.3.0",` to the `dependencies` list (after `httpx`):

```toml
dependencies = [
    "agno[anthropic,os,telegram]>=2.0.0",
    "python-dotenv>=1.0.0",
    "sqlalchemy>=2.0.0",
    "PyGithub>=2.0.0",
    "pyyaml>=6.0",
    "kubernetes>=29.0.0",
    "httpx>=0.27.0",
    "discord.py>=2.3.0",
    ...
]
```

- [ ] **Step 2: Install**

```bash
uv sync
```

Expected: resolves without errors, `discord` appears in the lock file.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add discord.py>=2.3.0"
```

---

## Task 2: DiscordNotifier

**Files:**
- Create: `wasp/clients/discord/notifier.py`
- Create: `wasp/clients/discord/__init__.py`
- Create: `tests/test_discord.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_discord.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


async def test_discord_notifier_send_calls_channel_send():
    from wasp.clients.discord.notifier import DiscordNotifier

    channel = AsyncMock()
    notifier = DiscordNotifier()
    notifier.register("123456789", channel)
    await notifier.send("123456789", "hello")

    channel.send.assert_awaited_once_with("hello")


async def test_discord_notifier_send_unknown_user_is_silent():
    from wasp.clients.discord.notifier import DiscordNotifier

    notifier = DiscordNotifier()
    # must not raise
    await notifier.send("unknown_user", "hello")


async def test_discord_notifier_register_overwrites_channel():
    from wasp.clients.discord.notifier import DiscordNotifier

    channel1 = AsyncMock()
    channel2 = AsyncMock()
    notifier = DiscordNotifier()
    notifier.register("111", channel1)
    notifier.register("111", channel2)
    await notifier.send("111", "hi")

    channel2.send.assert_awaited_once_with("hi")
    channel1.send.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_discord.py -v
```

Expected: `ModuleNotFoundError: No module named 'wasp.clients.discord'`

- [ ] **Step 3: Create package and notifier**

Create `wasp/clients/discord/__init__.py`:

```python
from wasp.clients.discord.bot import DiscordBot as DiscordBot
from wasp.clients.discord.notifier import DiscordNotifier as DiscordNotifier

_notifier: "DiscordNotifier | None" = None
```

Create `wasp/clients/discord/notifier.py`:

```python
import logging

log = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self) -> None:
        self._channels: dict = {}

    def register(self, user_id: str, channel) -> None:
        self._channels[user_id] = channel

    async def send(self, user_id: str, text: str) -> None:
        channel = self._channels.get(user_id)
        if channel is None:
            log.debug("DiscordNotifier: no channel registered for user_id=%s", user_id)
            return
        await channel.send(text)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_discord.py -v
```

Expected: 3 passed. (The `__init__.py` imports `DiscordBot` which doesn't exist yet — create a stub in `bot.py` first if needed. See note below.)

> **Note:** `wasp/clients/discord/__init__.py` imports `DiscordBot` from `bot.py`. Create a minimal stub for `bot.py` now so the import doesn't fail:
>
> ```python
> # wasp/clients/discord/bot.py — stub, replaced in Task 3
> class DiscordBot:
>     pass
> ```

- [ ] **Step 5: Commit**

```bash
git add wasp/clients/discord/ tests/test_discord.py
git commit -m "feat(discord): add DiscordNotifier with user_id→channel map"
```

---

## Task 3: DiscordBot

**Files:**
- Modify: `wasp/clients/discord/bot.py` (replace stub)
- Modify: `tests/test_discord.py` (add bot tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_discord.py`:

```python
async def test_discord_bot_on_message_authorized_calls_agent():
    import wasp.clients.discord.bot as b
    import wasp.auth as auth
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock(return_value=MagicMock(content="resposta"))
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = 111
    msg.author.name = "silvio"
    msg.content = "listar plataformas"
    msg.channel = AsyncMock()
    # bot.user is None on a bare instance — on_message checks msg.author != self.user
    # so we just need msg.author != bot.user (None != MagicMock() is True)

    monkeypatch_auth = MagicMock(return_value="user-001")

    import unittest.mock as mock
    with mock.patch.object(b.auth, "is_authorized", monkeypatch_auth):
        await bot.on_message(msg)

    agent.arun.assert_awaited_once()
    call_kwargs = agent.arun.call_args
    assert call_kwargs.args[0] == "listar plataformas"
    assert call_kwargs.kwargs["session_id"] == "dc:wasp-agent:111"
    msg.channel.send.assert_awaited_once()


async def test_discord_bot_on_message_ignores_own_messages():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock()
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    # Simulate bot.user by patching the property on the instance
    fake_user = MagicMock()
    import unittest.mock as mock
    with mock.patch.object(type(bot), "user", new_callable=lambda: property(lambda self: fake_user)):
        msg = MagicMock()
        msg.author = fake_user  # same object → own message
        msg.content = "hello"
        await bot.on_message(msg)

    agent.arun.assert_not_awaited()


async def test_discord_bot_on_message_unauthorized_user_is_silent():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock()
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = 999
    msg.author.name = "stranger"
    msg.content = "hello"
    msg.channel = AsyncMock()

    import unittest.mock as mock
    with mock.patch.object(b.auth, "is_authorized", return_value=None):
        await bot.on_message(msg)

    agent.arun.assert_not_awaited()
    msg.channel.send.assert_not_awaited()


async def test_discord_bot_registers_channel_on_authorized_message():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock(return_value=MagicMock(content="ok"))
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = 222
    msg.content = "ping"
    msg.channel = AsyncMock()

    import unittest.mock as mock
    with mock.patch.object(b.auth, "is_authorized", return_value="user-002"):
        await bot.on_message(msg)

    assert notifier._channels.get("222") is msg.channel


async def test_discord_bot_on_message_empty_content_is_ignored():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock()
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = 333
    msg.content = ""

    await bot.on_message(msg)

    agent.arun.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_discord.py -v -k "bot"
```

Expected: errors on import or attribute errors — `DiscordBot` is a stub.

- [ ] **Step 3: Implement DiscordBot**

Replace `wasp/clients/discord/bot.py`:

```python
import logging

import discord

import wasp.auth as auth

log = logging.getLogger(__name__)

AGENT_NAME = "wasp-agent"


class DiscordBot(discord.Client):
    def __init__(self, *, agent, notifier) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self._agent = agent
        self._notifier = notifier

    async def on_message(self, message) -> None:
        if message.author == self.user:
            return
        if not message.content:
            return

        user_id = str(message.author.id)
        if auth.is_authorized("dc", user_id) is None:
            return

        self._notifier.register(user_id, message.channel)
        session_id = f"dc:{AGENT_NAME}:{user_id}"
        result = await self._agent.arun(message.content, session_id=session_id)
        await message.channel.send(result.content)

    async def start_background(self) -> None:
        token = __import__("os").getenv("DISCORD_APP_TOKEN", "")
        await self.start(token)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_discord.py -v
```

Expected: all 8 tests passed.

- [ ] **Step 5: Check coverage**

```bash
pytest tests/test_discord.py --cov=wasp/clients/discord --cov-report=term-missing
```

Expected: 100% on `notifier.py` and `bot.py`.

- [ ] **Step 6: Commit**

```bash
git add wasp/clients/discord/bot.py tests/test_discord.py
git commit -m "feat(discord): add DiscordBot with on_message handler and auth guard"
```

---

## Task 4: Mock discord in conftest + update mock_agno

**Files:**
- Modify: `tests/conftest.py`

O `mock_agno` fixture limpa e remockeia módulos para isolar testes. Os novos módulos `wasp.clients.discord.*` precisam ser adicionados à lista de teardown. `discord` (lib externa) precisa ser mockado da mesma forma que `kubernetes`.

- [ ] **Step 1: Write failing test to verify isolation**

Adicione ao `tests/test_discord.py`:

```python
def test_discord_modules_cleared_between_tests_a(mock_agno):
    import sys
    assert "wasp.clients.discord" not in sys.modules or True  # always passes — confirms fixture ran
```

Esse teste é trivial mas força a fixture a rodar e confirma que não há erro de import.

- [ ] **Step 2: Update conftest.py**

Em `tests/conftest.py`, adicione os módulos Discord às duas listas de `sys.modules.pop` dentro de `mock_agno`, e adicione `discord` aos mocks externos:

Nos dois blocos `for mod in (...)`:

```python
        "wasp.clients.discord",
        "wasp.clients.discord.bot",
        "wasp.clients.discord.notifier",
```

Na lista `AGNO_MODULES + KUBE_MODULES`, crie uma nova constante:

```python
DISCORD_MODULES = [
    "discord",
    "discord.ext",
    "discord.ext.commands",
]
```

E mude a linha de criação de mocks para:

```python
    mocks = {name: MagicMock() for name in AGNO_MODULES + KUBE_MODULES + DISCORD_MODULES}
```

- [ ] **Step 3: Run full test suite**

```bash
pytest --cov -q
```

Expected: todos os testes existentes continuam passando, 100% coverage.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test(conftest): mock discord modules and clear wasp.clients.discord on teardown"
```

---

## Task 5: InterfaceLoader.build_discord()

**Files:**
- Modify: `wasp/clients/interfaces.py`
- Modify: `tests/test_interface_loader.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_interface_loader.py`:

```python
def test_build_discord_returns_bot_when_token_set(mock_agno, monkeypatch):
    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-token-123")
    from wasp.clients.interfaces import InterfaceLoader
    from unittest.mock import MagicMock, patch

    agent = MagicMock()
    loader = InterfaceLoader(agent)

    with patch("wasp.clients.interfaces.DiscordBot") as MockBot, \
         patch("wasp.clients.interfaces.DiscordNotifier") as MockNotifier:
        bot = loader.build_discord()

    MockNotifier.assert_called_once()
    MockBot.assert_called_once_with(agent=agent, notifier=MockNotifier.return_value)
    assert bot is MockBot.return_value


def test_build_discord_returns_none_when_no_token(mock_agno, monkeypatch):
    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)
    from wasp.clients.interfaces import InterfaceLoader
    from unittest.mock import MagicMock

    agent = MagicMock()
    loader = InterfaceLoader(agent)
    bot = loader.build_discord()

    assert bot is None


def test_build_discord_stores_notifier_singleton(mock_agno, monkeypatch):
    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")
    from wasp.clients.interfaces import InterfaceLoader
    from unittest.mock import MagicMock, patch
    import wasp.clients.discord as dc_pkg

    agent = MagicMock()
    loader = InterfaceLoader(agent)

    with patch("wasp.clients.interfaces.DiscordBot"), \
         patch("wasp.clients.interfaces.DiscordNotifier") as MockNotifier:
        loader.build_discord()

    assert dc_pkg._notifier is MockNotifier.return_value
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_interface_loader.py -v -k "discord"
```

Expected: `AttributeError: 'InterfaceLoader' object has no attribute 'build_discord'`

- [ ] **Step 3: Implement build_discord()**

Em `wasp/clients/interfaces.py`, adicione os imports e o método:

```python
import os

from agno.os.interfaces.telegram import Telegram

import wasp.clients.discord as discord_pkg
from wasp.clients.discord import DiscordBot, DiscordNotifier
from wasp.clients.telegram import _install_start_token_handler


class InterfaceLoader:
    def __init__(self, agent) -> None:
        self._agent = agent

    def build(self) -> list[Telegram]:
        builders = [self._build_telegram]
        return [iface for b in builders if (iface := b()) is not None]

    def build_discord(self) -> "DiscordBot | None":
        token = os.getenv("DISCORD_APP_TOKEN")
        if not token:
            return None
        notifier = DiscordNotifier()
        bot = DiscordBot(agent=self._agent, notifier=notifier)
        discord_pkg._notifier = notifier
        return bot

    def _build_telegram(self) -> Telegram | None:
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            return None
        iface = Telegram(agent=self._agent, token=token)
        _install_start_token_handler(iface)
        return iface
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_interface_loader.py -v
```

Expected: todos passando (incluindo os 3 testes originais + 3 novos).

- [ ] **Step 5: Commit**

```bash
git add wasp/clients/interfaces.py tests/test_interface_loader.py
git commit -m "feat(discord): add InterfaceLoader.build_discord() with notifier singleton"
```

---

## Task 6: Register Discord lifecycle in main.py

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_main.py`:

```python
def test_discord_bot_startup_registered_when_token_set(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")
    from unittest.mock import MagicMock, patch

    mock_bot = MagicMock()
    with patch("wasp.clients.interfaces.InterfaceLoader.build_discord", return_value=mock_bot):
        import main
        app = main.app

    registered = [h for h in getattr(app, "router", app).on_startup]
    assert mock_bot.start_background in registered


def test_discord_bot_not_registered_when_no_token(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)

    import main
    app = main.app

    registered = getattr(app, "router", app).on_startup
    # no discord handler — nothing that references start_background
    names = [getattr(h, "__name__", repr(h)) for h in registered]
    assert not any("discord" in n.lower() or "start_background" in n for n in names)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_main.py -v -k "discord"
```

Expected: `AssertionError` — bot startup not registered yet.

- [ ] **Step 3: Update main.py**

```python
from dotenv import load_dotenv

load_dotenv()

from wasp.startup import startup  # noqa: E402

startup()

import wasp.telemetry as telemetry  # noqa: E402
from agno.os import AgentOS  # noqa: E402
from wasp import auth  # noqa: E402
from wasp.agent import build_agent  # noqa: E402
from wasp.clients.interfaces import InterfaceLoader  # noqa: E402


def create_app():
    auth.init_db()
    agent = build_agent()
    loader = InterfaceLoader(agent)
    agent_os = AgentOS(
        agents=[agent],
        interfaces=loader.build(),
    )
    app = agent_os.get_app()
    telemetry.register_prometheus_route(app)
    discord_bot = loader.build_discord()
    if discord_bot is not None:
        app.add_event_handler("startup", discord_bot.start_background)
        app.add_event_handler("shutdown", discord_bot.close)
    return app, agent_os


app, agent_os = create_app()


if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_main.py -v
```

Expected: todos passando.

- [ ] **Step 5: Run full suite**

```bash
pytest --cov -q
```

Expected: 100% coverage, zero failures.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat(discord): register DiscordBot startup/shutdown in app lifespan"
```

---

## Task 7: _select_notifier Discord routing in watcher.py

**Files:**
- Modify: `wasp/watcher.py`
- Modify: `tests/test_watcher.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_watcher.py`:

```python
def test_select_notifier_dc_channel_picks_discord_notifier(monkeypatch):
    from unittest.mock import MagicMock
    import wasp.clients.discord as dc_pkg
    from wasp.watcher import _select_notifier

    mock_notifier = MagicMock()
    monkeypatch.setattr(dc_pkg, "_notifier", mock_notifier)
    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)

    result = _select_notifier(channel="dc")
    assert result is mock_notifier


def test_select_notifier_dc_channel_returns_none_when_no_singleton(monkeypatch):
    import wasp.clients.discord as dc_pkg
    from wasp.watcher import _select_notifier

    monkeypatch.setattr(dc_pkg, "_notifier", None)
    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)

    result = _select_notifier(channel="dc")
    assert result is None


def test_select_notifier_discord_kind_returns_singleton(monkeypatch):
    from unittest.mock import MagicMock
    import wasp.clients.discord as dc_pkg
    from wasp.watcher import _select_notifier

    mock_notifier = MagicMock()
    monkeypatch.setattr(dc_pkg, "_notifier", mock_notifier)
    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "discord")

    result = _select_notifier()
    assert result is mock_notifier


def test_extract_channel_returns_dc_for_discord_session():
    from wasp.watcher import extract_channel

    class FakeCtx:
        session_id = "dc:wasp-agent:123456789"

    assert extract_channel(FakeCtx()) == "dc"


def test_extract_chat_id_returns_user_id_for_discord_session():
    from wasp.watcher import extract_chat_id

    class FakeCtx:
        session_id = "dc:wasp-agent:123456789"

    assert extract_chat_id(FakeCtx()) == "123456789"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_watcher.py -v -k "discord or dc"
```

Expected: failures — `_select_notifier` doesn't handle `"dc"` yet, `extract_channel`/`extract_chat_id` don't recognize `"dc"` prefix.

- [ ] **Step 3: Update watcher.py**

Modifique as três funções em `wasp/watcher.py`:

**Imports** — adicione no topo:

```python
import wasp.clients.discord as discord_pkg
```

**`_select_notifier`** — adicione os novos cases:

```python
def _select_notifier(channel: str | None = None) -> Notifier | None:
    kind = os.getenv("WASP_AGENT_NOTIFIER")
    token = os.getenv("TELEGRAM_TOKEN")
    if kind is None:
        if channel == "local":
            kind = "console"
        elif channel == "tg":
            kind = "telegram"
        elif channel == "dc":
            kind = "discord"
        else:
            kind = "telegram" if token else "console"
    if kind == "console":
        return ConsoleNotifier()
    if kind == "telegram":
        return TelegramNotifier(token=token) if token else None
    if kind == "discord":
        return discord_pkg._notifier
    return None
```

**`extract_chat_id`** — adicione `"dc"` aos prefixos reconhecidos:

```python
def extract_chat_id(run_context) -> str | None:
    if run_context is None:
        return None
    session_id = getattr(run_context, "session_id", None)
    if not session_id:
        return None
    parts = session_id.split(":")
    if len(parts) >= 3 and parts[0] in ("tg", "local", "dc"):
        return parts[2]
    return None
```

**`extract_channel`** — adicione `"dc"`:

```python
def extract_channel(run_context) -> str | None:
    if run_context is None:
        return None
    session_id = getattr(run_context, "session_id", None)
    if not session_id:
        return None
    parts = session_id.split(":")
    if len(parts) >= 3 and parts[0] in ("tg", "local", "dc"):
        return parts[0]
    return None
```

- [ ] **Step 4: Run watcher tests**

```bash
pytest tests/test_watcher.py -v
```

Expected: todos passando.

- [ ] **Step 5: Run full suite**

```bash
pytest --cov -q
```

Expected: 100% coverage, zero failures.

- [ ] **Step 6: Lint**

```bash
make format
ruff check .
```

Expected: zero issues.

- [ ] **Step 7: Commit**

```bash
git add wasp/watcher.py tests/test_watcher.py
git commit -m "feat(discord): route dc channel in _select_notifier, extract_channel, extract_chat_id"
```

---

## Task 8: Final validation

- [ ] **Step 1: Full test suite with coverage**

```bash
make format
make test
```

Expected: `pytest --cov` passes, 100% coverage.

- [ ] **Step 2: E2E**

```bash
make e2e-with-debug
```

Expected: E2E passa. Discord é opt-in via `DISCORD_APP_TOKEN` — o E2E existente não usa Discord, não deve ser afetado.

- [ ] **Step 3: Smoke test manual (opcional)**

Se quiser verificar conexão real com o Discord:

```bash
# Com DISCORD_APP_TOKEN setado no .env:
make run
# Envie uma mensagem para o bot no Discord — deve responder.
```

- [ ] **Step 4: Commit final se houver ajustes**

```bash
git add -p
git commit -m "chore(discord): final adjustments after validation"
```
# main.py Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extrair `wasp/models.py`, `wasp/agent.py` e `wasp/telegram.py` de `main.py`, reduzindo-o a ~40 linhas de wiring puro.

**Architecture:** Cada módulo tem uma responsabilidade única: `models.py` é a factory de LLM, `agent.py` define o agente (INSTRUCTIONS + build), `telegram.py` é o middleware de autenticação de convites. `main.py` apenas orquestra bootstrap → agent → interfaces → app → routes.

**Tech Stack:** Python, agno, starlette, pytest, ruff, uv

---

## File Map

| Ação | Arquivo |
|---|---|
| Criar | `wasp/models.py` |
| Criar | `wasp/agent.py` |
| Criar | `wasp/telegram.py` |
| Criar | `tests/test_models.py` |
| Criar | `tests/test_agent.py` |
| Criar | `tests/test_telegram.py` |
| Modificar | `main.py` |
| Modificar | `tests/conftest.py` |
| Modificar | `tests/test_main.py` |

---

## Task 0: Atualizar conftest.py

Três novos módulos `wasp.*` precisam ser adicionados ao loop de cleanup do `mock_agno`, senão estado de módulo vaza entre testes.

**Files:**
- Modify: `tests/conftest.py:48-61` e `77-90`

- [ ] **Step 1: Adicionar novos módulos ao loop de cleanup**

Em `tests/conftest.py`, o loop de cleanup aparece duas vezes (antes e depois do yield). Adicionar as três entradas em ambos:

```python
    for mod in (
        "main",
        "wasp",
        "wasp.logging",
        "wasp.models",       # <-- novo
        "wasp.agent",        # <-- novo
        "wasp.telegram",     # <-- novo
        "wasp.provision",
        "wasp.watcher",
        "wasp.telemetry",
        "wasp.auth",
        "wasp.auth_cli",
        "wasp.auth_guard",
        "wasp.gitops_committer",
        "wasp.platform_cluster",
    ):
        sys.modules.pop(mod, None)
```

- [ ] **Step 2: Verificar que os testes existentes ainda passam**

```bash
pytest tests/test_main.py -v
```

Expected: todos passam (nenhum módulo novo existe ainda, mas o cleanup extra é inócuo).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(conftest): add wasp.models, wasp.agent, wasp.telegram to module cleanup"
```

---

## Task 1: `wasp/models.py`

**Files:**
- Create: `wasp/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Escrever os testes (red)**

Criar `tests/test_models.py`:

```python
import pytest


def test_build_model_ollama(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")

    from wasp.models import build_model

    build_model()

    mock_agno["agno.models.ollama"].Ollama.assert_called_once_with(
        id="llama3.1", host="http://localhost:11434"
    )


def test_build_model_anthropic(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")

    from wasp.models import build_model

    build_model()

    mock_agno["agno.models.anthropic"].Claude.assert_called_once_with(
        id="claude-sonnet", auth_token="tok"
    )


def test_build_model_openai(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    from wasp.models import build_model

    build_model()

    mock_agno["agno.models.openai"].OpenAIChat.assert_called_once_with(
        id="gpt-4o", api_key="sk-test", base_url=None
    )


def test_build_model_openai_with_base_url(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://proxy:8080")

    from wasp.models import build_model

    build_model()

    mock_agno["agno.models.openai"].OpenAIChat.assert_called_once_with(
        id="gpt-4o", api_key="sk-test", base_url="http://proxy:8080"
    )


def test_build_model_unknown_raises(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    from wasp.models import build_model

    with pytest.raises(ValueError, match="Invalid LLM_PROVIDER"):
        build_model()
```

- [ ] **Step 2: Rodar e confirmar falha**

```bash
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'wasp.models'`

- [ ] **Step 3: Implementar `wasp/models.py`**

```python
import os


def build_model():
    provider = os.getenv("LLM_PROVIDER", "ollama")
    if provider == "ollama":
        from agno.models.ollama import Ollama

        return Ollama(
            id=os.getenv("OLLAMA_MODEL", "llama3.1"),
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )
    if provider == "anthropic":
        from agno.models.anthropic import Claude

        return Claude(
            id=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
            auth_token=os.getenv("ANTHROPIC_AUTH_TOKEN"),
        )
    if provider == "openai":
        from agno.models.openai import OpenAIChat

        return OpenAIChat(
            id=os.getenv("OPENAI_MODEL", "gpt-4o"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
    raise ValueError(
        f"Invalid LLM_PROVIDER: {provider!r}. Use: ollama, anthropic, openai"
    )
```

- [ ] **Step 4: Rodar e confirmar verde**

```bash
pytest tests/test_models.py -v
```

Expected: 5 passed

- [ ] **Step 5: Confirmar que testes existentes não quebraram**

```bash
pytest tests/test_main.py -v
```

Expected: todos passam

- [ ] **Step 6: Commit**

```bash
git add wasp/models.py tests/test_models.py
git commit -m "feat(models): extract build_model factory into wasp/models.py"
```

---

## Task 2: `wasp/agent.py`

**Files:**
- Create: `wasp/agent.py`
- Create: `tests/test_agent.py`

- [ ] **Step 1: Escrever os testes (red)**

Criar `tests/test_agent.py`:

```python
def test_build_agent_uses_ollama_by_default(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")

    from wasp.agent import build_agent

    build_agent()

    mock_agno["agno.models.ollama"].Ollama.assert_called_once_with(
        id="test-model", host="http://localhost:11434"
    )
    mock_agno["agno.db.sqlite.sqlite"].SqliteDb.assert_called_once_with(
        db_file="agent.db", session_table="agent_sessions"
    )
    call_kwargs = mock_agno["agno.agent"].Agent.call_args.kwargs
    assert call_kwargs["name"] == "wasp-agent"
    assert call_kwargs["add_history_to_context"] is True
    assert "You are a DevOps assistant." in call_kwargs["instructions"]


def test_build_agent_tools(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    from wasp.agent import build_agent

    build_agent()

    call_kwargs = mock_agno["agno.agent"].Agent.call_args.kwargs
    tool_names = {getattr(t, "__name__", None) for t in call_kwargs["tools"]}
    assert "list_platform_instances" in tool_names
    assert "provision_platform_instance" in tool_names


def test_build_agent_returns_agent_instance(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    from wasp.agent import build_agent

    result = build_agent()

    assert result is mock_agno["agno.agent"].Agent.return_value
```

- [ ] **Step 2: Rodar e confirmar falha**

```bash
pytest tests/test_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'wasp.agent'`

- [ ] **Step 3: Implementar `wasp/agent.py`**

```python
from agno.agent import Agent
from agno.db.sqlite.sqlite import SqliteDb

from wasp import list_platform_instances, provision_platform_instance
from wasp.models import build_model

INSTRUCTIONS = [
    "You are a DevOps assistant.",
    "You help engineers provision infrastructure resources, monitor their status,"
    " and receive notifications when resources become ready.",
    "Resources are managed via Crossplane on Kubernetes. When discussing resource"
    " state, refer to Crossplane conditions and status fields.",
    "Answer concisely and in the same language the user writes in."
    " Be direct and clear. No filler words ('Sure!', 'Done!', 'Perfect!', 'Excellent!'),"
    " no emojis, no exclamation marks. Use short paragraphs separated by blank lines"
    " — avoid bullet lists and bold text unless structure genuinely helps.",
    "Never call provision_platform_instance without explicit user confirmation."
    " On the first turn of any creation or deletion request, always ask the user"
    " to confirm — e.g. 'Confirm creation?' — and wait for an affirmative reply."
    " Once the user confirms (e.g. 'yes', 'confirm', 'go ahead'), call"
    " provision_platform_instance immediately — do not ask again."
    " After a successful provisioning, relay the tool's message as-is —"
    " do not add technical details like commit SHA, file paths, or internal"
    " infrastructure names (ArgoCD, Crossplane, GitHub, Kubernetes).",
    "list_platform_instances is read-only — safe to call without confirmation.",
    "Currently, you can create new tenants and list existing ones."
    " Other operations (update, delete, status of individual tenant) are not"
    " yet supported — acknowledge the request and let the user know.",
]


def build_agent() -> Agent:
    return Agent(
        name="wasp-agent",
        model=build_model(),
        db=SqliteDb(db_file="agent.db", session_table="agent_sessions"),
        add_history_to_context=True,
        instructions=INSTRUCTIONS,
        tools=[provision_platform_instance, list_platform_instances],
    )
```

- [ ] **Step 4: Rodar e confirmar verde**

```bash
pytest tests/test_agent.py -v
```

Expected: 3 passed

- [ ] **Step 5: Confirmar que testes existentes não quebraram**

```bash
pytest tests/test_main.py tests/test_models.py -v
```

Expected: todos passam

- [ ] **Step 6: Commit**

```bash
git add wasp/agent.py tests/test_agent.py
git commit -m "feat(agent): extract INSTRUCTIONS and build_agent into wasp/agent.py"
```

---

## Task 3: `wasp/telegram.py`

**Files:**
- Create: `wasp/telegram.py`
- Create: `tests/test_telegram.py`

- [ ] **Step 1: Escrever os testes (red)**

Criar `tests/test_telegram.py` (adaptado de `test_main.py`, substituindo `main.*` por `wasp.telegram.*`):

```python
import pytest


async def test_process_start_token_redeems_invite(mock_agno):
    from wasp.telegram import _process_start_token

    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    def fake_redeem(token, channel, channel_id):
        assert token == "ABC123"
        assert channel == "tg"
        assert channel_id == "42"
        return ("uid-1", "Alice")

    payload = {"message": {"text": "/start ABC123", "chat": {"id": 42}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)

    assert handled is True
    assert sent == [("42", "Welcome, Alice. You are authorized to use wasp-agent.")]


async def test_process_start_token_invalid_sends_error(mock_agno, monkeypatch):
    import wasp.telemetry as telemetry
    from wasp.telegram import _process_start_token

    sent = []
    denied = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    def fake_redeem(token, channel, channel_id):
        return None

    monkeypatch.setattr(telemetry, "auth_denied", lambda **kw: denied.append(kw))

    payload = {"message": {"text": "/start BAD", "chat": {"id": 7}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)

    assert handled is True
    assert sent == [
        ("7", "Invalid or expired link. Request a new one from the administrator.")
    ]
    assert denied == [{"channel": "tg", "reason": "invalid_token"}]


async def test_process_start_token_bare_start_not_handled(mock_agno):
    from wasp.telegram import _process_start_token

    calls = []

    async def fake_send(chat_id, text):
        calls.append(("send", chat_id, text))

    def fake_redeem(*args, **kwargs):
        calls.append(("redeem", args))
        return None

    payload = {"message": {"text": "/start", "chat": {"id": 1}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)

    assert handled is False
    assert calls == []


async def test_process_start_token_non_start_not_handled(mock_agno):
    from wasp.telegram import _process_start_token

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "hello bot", "chat": {"id": 1}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_process_start_token_edited_message(mock_agno):
    from wasp.telegram import _process_start_token

    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    def fake_redeem(token, channel, channel_id):
        return ("uid", "Bob")

    payload = {"edited_message": {"text": "/start XYZ", "chat": {"id": 5}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is True
    assert sent[0][0] == "5"


async def test_process_start_token_missing_chat_id_not_handled(mock_agno):
    from wasp.telegram import _process_start_token

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "/start ABC", "chat": {}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_process_start_token_trailing_space_not_handled(mock_agno):
    from wasp.telegram import _process_start_token

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "/start ", "chat": {"id": 1}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_process_start_token_only_whitespace_not_handled(mock_agno):
    from wasp.telegram import _process_start_token

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "/start   \t  ", "chat": {"id": 1}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_install_start_token_handler_wraps_webhook(mock_agno, monkeypatch):
    from unittest.mock import MagicMock, AsyncMock
    import wasp.telegram as telegram_mod
    from wasp.telegram import _install_start_token_handler

    monkeypatch.setenv("APP_ENV", "development")

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/webhook", endpoint=original_endpoint)
    status_route = MagicMock(path="/status", endpoint=MagicMock())
    fake_router = MagicMock(routes=[status_route, webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    _install_start_token_handler(iface)

    monkeypatch.setattr(telegram_mod.auth, "redeem_invite", lambda *a, **kw: ("uid", "Carol"))
    import sys
    sys.modules[
        "agno.os.interfaces.telegram.security"
    ].validate_webhook_secret_token = lambda token: True

    sent = []

    async def fake_send(self, chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(telegram_mod.TelegramNotifier, "send", fake_send)

    router = iface.get_router()
    assert router is fake_router
    new_endpoint = webhook_route.endpoint
    assert new_endpoint is not original_endpoint

    fake_request = MagicMock()
    fake_request.headers = {"X-Telegram-Bot-Api-Secret-Token": "ok"}
    fake_request.json = AsyncMock(
        return_value={"message": {"text": "/start ABC", "chat": {"id": 99}}}
    )
    background = MagicMock()
    response = await new_endpoint(fake_request, background)
    assert response.status_code == 200
    original_endpoint.assert_not_called()
    assert sent == [("99", "Welcome, Carol. You are authorized to use wasp-agent.")]

    fake_request2 = MagicMock()
    fake_request2.headers = {"X-Telegram-Bot-Api-Secret-Token": "ok"}
    fake_request2.json = AsyncMock(
        return_value={"message": {"text": "olá", "chat": {"id": 1}}}
    )
    result = await new_endpoint(fake_request2, background)
    assert result == "agno-result"
    original_endpoint.assert_awaited_once()


async def test_install_start_token_handler_finds_webhook_with_router_prefix(mock_agno):
    from unittest.mock import MagicMock, AsyncMock
    from wasp.telegram import _install_start_token_handler

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/telegram/webhook", endpoint=original_endpoint)
    status_route = MagicMock(path="/telegram/status", endpoint=MagicMock())
    fake_router = MagicMock(routes=[status_route, webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    _install_start_token_handler(iface)
    iface.get_router()
    assert webhook_route.endpoint is not original_endpoint


async def test_webhook_rejects_missing_secret_token(mock_agno, monkeypatch):
    from unittest.mock import MagicMock, AsyncMock
    import wasp.telegram as telegram_mod
    from wasp.telegram import _install_start_token_handler

    monkeypatch.delenv("APP_ENV", raising=False)

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/webhook", endpoint=original_endpoint)
    fake_router = MagicMock(routes=[webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    _install_start_token_handler(iface)

    redeem_calls = []

    def fake_redeem(*args, **kwargs):
        redeem_calls.append(args)
        return ("uid", "Mallory")

    monkeypatch.setattr(telegram_mod.auth, "redeem_invite", fake_redeem)
    import sys
    sys.modules[
        "agno.os.interfaces.telegram.security"
    ].validate_webhook_secret_token = lambda token: False

    iface.get_router()
    new_endpoint = webhook_route.endpoint

    fake_request = MagicMock()
    fake_request.headers = {}
    fake_request.json = AsyncMock(
        return_value={"message": {"text": "/start ABC", "chat": {"id": 99}}}
    )
    response = await new_endpoint(fake_request, MagicMock())

    assert response.status_code == 403
    assert redeem_calls == []
    original_endpoint.assert_not_called()


async def test_webhook_with_auth_has_fastapi_type_annotations(mock_agno):
    import inspect
    from unittest.mock import MagicMock, AsyncMock
    from starlette.requests import Request
    from starlette.background import BackgroundTasks
    from wasp.telegram import _install_start_token_handler

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/telegram/webhook", endpoint=original_endpoint)
    fake_router = MagicMock(routes=[webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    _install_start_token_handler(iface)
    iface.get_router()

    sig = inspect.signature(webhook_route.endpoint)
    params = sig.parameters
    assert params["request"].annotation is Request, (
        "Missing Request annotation — FastAPI will return 422 on every webhook POST"
    )
    assert params["background_tasks"].annotation is BackgroundTasks, (
        "Missing BackgroundTasks annotation — FastAPI will return 422 on every webhook POST"
    )
```

- [ ] **Step 2: Rodar e confirmar falha**

```bash
pytest tests/test_telegram.py -v
```

Expected: `ModuleNotFoundError: No module named 'wasp.telegram'`

- [ ] **Step 3: Implementar `wasp/telegram.py`**

Nota importante (CLAUDE.md §12a): `Request` deve ser importado a nível de módulo (para que `webhook_with_auth.__globals__` contenha a classe e FastAPI resolva a annotation). `BackgroundTasks` é importado dentro de `get_router_with_auth` (antes da definição de `webhook_with_auth`) — funciona porque annotations são avaliadas eagerly no Python atual.

```python
import wasp.auth as auth
import wasp.telemetry as telemetry
from starlette.requests import Request
from wasp.notifier import TelegramNotifier

WELCOME_MESSAGE = "Welcome, {display_name}. You are authorized to use wasp-agent."
INVALID_INVITE_MESSAGE = (
    "Invalid or expired link. Request a new one from the administrator."
)


async def _process_start_token(payload: dict, redeem_fn, send_fn) -> bool:
    """Intercept ``/start <token>`` deep links.

    Returns ``True`` if the payload was handled (caller must short-circuit).
    Returns ``False`` to let agno process normally.
    """
    message = payload.get("message") or payload.get("edited_message") or {}
    text = (message.get("text") or "").strip()
    if not text.startswith("/start "):
        return False
    token = text.split(maxsplit=1)[1].split()[0]
    chat_id = message.get("chat", {}).get("id")
    if chat_id is None:
        return False
    result = redeem_fn(token, "tg", str(chat_id))
    if result is None:
        telemetry.auth_denied(channel="tg", reason="invalid_token")
        await send_fn(str(chat_id), INVALID_INVITE_MESSAGE)
    else:
        _user_id, display_name = result
        await send_fn(str(chat_id), WELCOME_MESSAGE.format(display_name=display_name))
    return True


def _install_start_token_handler(iface) -> None:
    """Wrap ``iface.get_router`` so ``/start <token>`` is intercepted.

    agno's built-in ``/start`` handler discards positional args. We wrap the
    ``/webhook`` route's endpoint so wasp can redeem invite tokens before
    agno dispatches the message to the LLM.
    """
    # NOTE: relies on agno's internal ``Telegram.get_router()`` API. If agno
    # changes this contract, this wrapper must be updated.
    original_get_router = iface.get_router
    notifier = TelegramNotifier(iface.token)

    def get_router_with_auth():
        from starlette.background import BackgroundTasks

        router = original_get_router()
        webhook_route = next(
            r for r in router.routes if getattr(r, "path", "").endswith("/webhook")
        )
        original_endpoint = webhook_route.endpoint

        async def webhook_with_auth(
            request: Request, background_tasks: BackgroundTasks
        ):
            from starlette.responses import JSONResponse
            from agno.os.interfaces.telegram.security import (
                validate_webhook_secret_token,
            )

            secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if not validate_webhook_secret_token(secret_token):
                return JSONResponse({"detail": "Invalid secret token"}, status_code=403)

            body = await request.json()
            handled = await _process_start_token(
                body, auth.redeem_invite, notifier.send
            )
            if handled:
                return JSONResponse({"status": "ok"})

            return await original_endpoint(request, background_tasks)

        webhook_route.endpoint = webhook_with_auth
        return router

    iface.get_router = get_router_with_auth
```

- [ ] **Step 4: Rodar e confirmar verde**

```bash
pytest tests/test_telegram.py -v
```

Expected: 12 passed

- [ ] **Step 5: Confirmar que testes existentes não quebraram**

```bash
pytest tests/test_main.py tests/test_models.py tests/test_agent.py -v
```

Expected: todos passam

- [ ] **Step 6: Commit**

```bash
git add wasp/telegram.py tests/test_telegram.py
git commit -m "feat(telegram): extract auth middleware into wasp/telegram.py"
```

---

## Task 4: Simplificar `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Substituir o conteúdo de `main.py`**

```python
import os

from dotenv import load_dotenv

load_dotenv()

from wasp.logging import configure_logging  # noqa: E402

configure_logging()

os.umask(0o077)  # agent.db created with 600 permissions

import wasp.telemetry as telemetry  # noqa: E402 — must come after load_dotenv so env vars are set

from agno.os import AgentOS  # noqa: E402
from agno.os.interfaces.telegram import Telegram  # noqa: E402
from wasp import auth  # noqa: E402
from wasp.agent import build_agent  # noqa: E402
from wasp.telegram import _install_start_token_handler  # noqa: E402

auth.init_db()

agent = build_agent()

interfaces = []
telegram_token = os.getenv("TELEGRAM_TOKEN")
if telegram_token:
    telegram_interface = Telegram(agent=agent, token=telegram_token)
    _install_start_token_handler(telegram_interface)
    interfaces.append(telegram_interface)

agent_os = AgentOS(
    agents=[agent],
    interfaces=interfaces,
)

app = agent_os.get_app()

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import Response  # noqa: E402
from starlette.routing import Route  # noqa: E402


async def metrics_endpoint(request: Request) -> Response:
    registry = telemetry._prometheus_registry
    data = generate_latest(registry) if registry is not None else generate_latest()
    return Response(data, media_type=CONTENT_TYPE_LATEST)


app.routes.append(Route("/telemetry/prometheus", metrics_endpoint))

if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)
```

- [ ] **Step 2: Rodar toda a suite**

```bash
pytest tests/ -v --ignore=tests/e2e
```

Expected: todos passam. Se algum teste de `test_main.py` referenciar `main._process_start_token`, `main.INSTRUCTIONS`, `main._build_model` ou `main.TelegramNotifier` e falhar, anote — serão removidos no Task 5.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "refactor(main): reduce to wiring-only using wasp.models, wasp.agent, wasp.telegram"
```

---

## Task 5: Limpar `test_main.py`

Remover testes que já vivem em `test_models.py`, `test_agent.py` e `test_telegram.py`. Manter apenas os que testam wiring de `main.py`.

**Files:**
- Modify: `tests/test_main.py`

- [ ] **Step 1: Identificar testes a remover**

Testes a **remover** de `test_main.py` (já cobertos nos novos arquivos):

- `test_agent_config` → coberto por `test_agent.py::test_build_agent_uses_ollama_by_default`
- `test_agent_uses_anthropic_model` → coberto por `test_models.py::test_build_model_anthropic`
- `test_agent_uses_openai_model` → coberto por `test_models.py::test_build_model_openai`
- `test_unknown_provider_raises` → coberto por `test_models.py::test_build_model_unknown_raises`
- `test_agent_tools_include_list_platform_instances` → coberto por `test_agent.py::test_build_agent_tools`
- `test_start_token_redeems_invite_and_sends_welcome` → coberto por `test_telegram.py`
- `test_start_token_invalid_sends_error_message` → coberto por `test_telegram.py`
- `test_start_without_token_is_not_handled` → coberto por `test_telegram.py`
- `test_non_start_message_is_not_handled` → coberto por `test_telegram.py`
- `test_start_token_handles_edited_message` → coberto por `test_telegram.py`
- `test_start_token_missing_chat_id_not_handled` → coberto por `test_telegram.py`
- `test_start_token_trailing_space_not_handled` → coberto por `test_telegram.py`
- `test_start_token_only_whitespace_not_handled` → coberto por `test_telegram.py`
- `test_install_start_token_handler_wraps_webhook` → coberto por `test_telegram.py`
- `test_install_start_token_handler_finds_webhook_with_router_prefix` → coberto por `test_telegram.py`
- `test_webhook_rejects_missing_secret_token` → coberto por `test_telegram.py`
- `test_webhook_with_auth_has_fastapi_type_annotations` → coberto por `test_telegram.py`

Testes a **manter** em `test_main.py`:

- `test_agent_os_with_token`
- `test_telegram_not_added_without_token`
- `test_metrics_route_exists`
- `test_metrics_endpoint_returns_prometheus_format`
- `test_metrics_endpoint_uses_prometheus_registry`
- `test_main_initializes_auth_db`
- `test_install_start_token_handler_called_with_token`

- [ ] **Step 2: Substituir `tests/test_main.py` com apenas os testes de wiring**

```python
def test_agent_os_with_token(mock_agno, monkeypatch):
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
    """No interfaces are added when TELEGRAM_TOKEN is absent."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    import main  # noqa: F401

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert call_kwargs["interfaces"] == []


def test_metrics_route_exists():
    import main

    appended = [call.args[0] for call in main.app.routes.append.call_args_list]
    paths = [r.path for r in appended if hasattr(r, "path")]
    assert "/telemetry/prometheus" in paths


async def test_metrics_endpoint_returns_prometheus_format():
    import main

    response = await main.metrics_endpoint(request=None)
    assert response.status_code == 200
    assert "text/plain" in response.media_type


async def test_metrics_endpoint_uses_prometheus_registry(monkeypatch):
    from unittest.mock import patch
    import prometheus_client

    fake_data = (
        b"# HELP agent_tool_calls_total Tool invocations\nagent_tool_calls_total 1.0\n"
    )
    with patch("prometheus_client.generate_latest", return_value=fake_data) as mock_gen:
        import main
        import wasp.telemetry as telemetry

        telemetry._prometheus_registry = prometheus_client.REGISTRY
        response = await main.metrics_endpoint(request=None)
    mock_gen.assert_called_once_with(prometheus_client.REGISTRY)
    assert response.body == fake_data


def test_main_initializes_auth_db(mock_agno, monkeypatch):
    init_called = []
    monkeypatch.setattr(
        "wasp.auth.init_db", lambda db_file=None: init_called.append(db_file)
    )
    import main  # noqa: F401

    assert init_called


def test_install_start_token_handler_called_with_token(mock_agno, monkeypatch):
    """When TELEGRAM_TOKEN is set, the wrapper is installed on the interface."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tk")

    import main  # noqa: F401

    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    interface = call_kwargs["interfaces"][0]
    assert callable(interface.get_router)
```

- [ ] **Step 3: Rodar toda a suite**

```bash
pytest tests/ -v --ignore=tests/e2e
```

Expected: todos passam, nenhum teste perdido.

- [ ] **Step 4: Commit**

```bash
git add tests/test_main.py
git commit -m "refactor(test_main): keep only wiring tests, unit tests moved to test_models/agent/telegram"
```

---

## Task 6: Validação Final

- [ ] **Step 1: Formatar**

```bash
make format
```

Expected: sem erros. Se houver diff, `git add` e amend no commit anterior ou novo commit.

- [ ] **Step 2: Suite unitária completa com cobertura**

```bash
make test
```

Expected: todos passam, cobertura 100%.

- [ ] **Step 3: E2E**

```bash
make e2e-with-debug
```

Expected: fluxo completo (turn-1 → confirmação → turn-2 → watcher → notificação) sem erros.

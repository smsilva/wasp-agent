# Clients Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganizar `wasp/notifier.py` e `wasp/telegram.py` no pacote `wasp/clients/` por canal, com `RecordingNotifier` movido para `tests/notifiers.py`.

**Architecture:** Criar subpacotes `wasp/clients/telegram/` e `wasp/clients/local/` com o `Notifier` Protocol em `wasp/clients/__init__.py`. Mover código sem alterar lógica; atualizar todos os imports; deletar os arquivos originais.

**Tech Stack:** Python 3.12+, pytest, ruff

---

## Mapa de arquivos

| Ação | Arquivo |
|---|---|
| Criar | `wasp/clients/__init__.py` |
| Criar | `wasp/clients/telegram/__init__.py` |
| Criar | `wasp/clients/telegram/notifier.py` |
| Criar | `wasp/clients/telegram/webhook.py` |
| Criar | `wasp/clients/local/__init__.py` |
| Criar | `wasp/clients/local/notifier.py` |
| Criar | `tests/notifiers.py` |
| Modificar | `wasp/watcher.py` |
| Modificar | `main.py` |
| Modificar | `tests/test_telegram.py` |
| Modificar | `tests/test_watcher.py` |
| Modificar | `tests/e2e/conftest.py` |
| Modificar | `tests/conftest.py` |
| Deletar | `wasp/notifier.py` |
| Deletar | `wasp/telegram.py` |
| Modificar | `CLAUDE.md` |

---

### Task 1: Criar `wasp/clients/__init__.py` com o Notifier Protocol

**Files:**
- Create: `wasp/clients/__init__.py`

- [ ] **Step 1: Criar o arquivo**

```python
from typing import Protocol


class Notifier(Protocol):
    async def send(self, chat_id: str, text: str) -> None: ...
```

- [ ] **Step 2: Verificar que o import funciona**

```bash
python -c "from wasp.clients import Notifier; print('OK')"
```
Esperado: `OK`

- [ ] **Step 3: Commit**

```bash
git add wasp/clients/__init__.py
git commit -m "feat(clients): add Notifier Protocol in wasp/clients"
```

---

### Task 2: Criar `wasp/clients/telegram/notifier.py` com TelegramNotifier

**Files:**
- Create: `wasp/clients/telegram/__init__.py` (vazio por ora)
- Create: `wasp/clients/telegram/notifier.py`

- [ ] **Step 1: Criar `wasp/clients/telegram/__init__.py` vazio**

```python
```

- [ ] **Step 2: Criar `wasp/clients/telegram/notifier.py`**

```python
import httpx


class TelegramNotifier:
    def __init__(self, token: str, base_url: str = "https://api.telegram.org"):
        self._token = token
        self._base_url = base_url

    async def send(self, chat_id: str, text: str) -> None:
        url = f"{self._base_url}/bot{self._token}/sendMessage"
        async with httpx.AsyncClient(timeout=10.0) as http:
            await http.post(url, json={"chat_id": chat_id, "text": text})
```

- [ ] **Step 3: Verificar import**

```bash
python -c "from wasp.clients.telegram.notifier import TelegramNotifier; print('OK')"
```
Esperado: `OK`

- [ ] **Step 4: Commit**

```bash
git add wasp/clients/telegram/__init__.py wasp/clients/telegram/notifier.py
git commit -m "feat(clients/telegram): add TelegramNotifier"
```

---

### Task 3: Criar `wasp/clients/telegram/webhook.py`

**Files:**
- Create: `wasp/clients/telegram/webhook.py`

- [ ] **Step 1: Criar o arquivo**

Conteúdo idêntico ao `wasp/telegram.py` atual, com o import de `TelegramNotifier` atualizado:

```python
import wasp.auth as auth
import wasp.telemetry as telemetry
from starlette.requests import Request
from wasp.clients.telegram.notifier import TelegramNotifier

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

            # Starlette's Request.json() caches `_json` on the instance after
            # first call; agno's downstream `await request.json()` reuses it.
            return await original_endpoint(request, background_tasks)

        webhook_route.endpoint = webhook_with_auth
        return router

    iface.get_router = get_router_with_auth
```

- [ ] **Step 2: Verificar import**

```bash
python -c "from wasp.clients.telegram.webhook import _install_start_token_handler; print('OK')"
```
Esperado: `OK`

- [ ] **Step 3: Commit**

```bash
git add wasp/clients/telegram/webhook.py
git commit -m "feat(clients/telegram): add webhook handler"
```

---

### Task 4: Preencher `wasp/clients/telegram/__init__.py` com re-exports

**Files:**
- Modify: `wasp/clients/telegram/__init__.py`

- [ ] **Step 1: Atualizar o arquivo**

```python
from wasp.clients.telegram.notifier import TelegramNotifier
from wasp.clients.telegram.webhook import _install_start_token_handler
```

- [ ] **Step 2: Verificar imports**

```bash
python -c "from wasp.clients.telegram import TelegramNotifier, _install_start_token_handler; print('OK')"
```
Esperado: `OK`

- [ ] **Step 3: Commit**

```bash
git add wasp/clients/telegram/__init__.py
git commit -m "feat(clients/telegram): add __init__ re-exports"
```

---

### Task 5: Criar `wasp/clients/local/` com ConsoleNotifier

**Files:**
- Create: `wasp/clients/local/__init__.py`
- Create: `wasp/clients/local/notifier.py`

- [ ] **Step 1: Criar `wasp/clients/local/notifier.py`**

```python
import logging

log = logging.getLogger(__name__)


class ConsoleNotifier:
    async def send(self, chat_id: str, text: str) -> None:
        log.info("[NOTIFIER chat_id=%s] %s", chat_id, text)
```

- [ ] **Step 2: Criar `wasp/clients/local/__init__.py`**

```python
from wasp.clients.local.notifier import ConsoleNotifier
```

- [ ] **Step 3: Verificar imports**

```bash
python -c "from wasp.clients.local import ConsoleNotifier; print('OK')"
```
Esperado: `OK`

- [ ] **Step 4: Commit**

```bash
git add wasp/clients/local/notifier.py wasp/clients/local/__init__.py
git commit -m "feat(clients/local): add ConsoleNotifier"
```

---

### Task 6: Criar `tests/notifiers.py` com RecordingNotifier

**Files:**
- Create: `tests/notifiers.py`

- [ ] **Step 1: Criar o arquivo**

```python
import asyncio


class RecordingNotifier:
    def __init__(self):
        self.messages: list[dict] = []

    async def send(self, chat_id: str, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})

    async def wait_for_message(self) -> None:
        while not self.messages:
            await asyncio.sleep(0.1)
```

- [ ] **Step 2: Verificar import**

```bash
python -c "from tests.notifiers import RecordingNotifier; print('OK')"
```
Esperado: `OK`

- [ ] **Step 3: Commit**

```bash
git add tests/notifiers.py
git commit -m "test: add RecordingNotifier to tests/notifiers.py"
```

---

### Task 7: Atualizar imports em `wasp/watcher.py`

**Files:**
- Modify: `wasp/watcher.py:12`

- [ ] **Step 1: Substituir a linha de import**

Linha atual (linha 12):
```python
from wasp.notifier import ConsoleNotifier, Notifier, TelegramNotifier
```

Substituir por:
```python
from wasp.clients import Notifier
from wasp.clients.local import ConsoleNotifier
from wasp.clients.telegram import TelegramNotifier
```

- [ ] **Step 2: Rodar os testes de watcher para verificar**

```bash
pytest tests/test_watcher.py -v 2>&1 | head -30
```
Esperado: alguns testes passam, alguns falham por imports antigos nos próprios testes (ainda ok neste passo).

- [ ] **Step 3: Commit**

```bash
git add wasp/watcher.py
git commit -m "refactor(watcher): update imports to wasp.clients"
```

---

### Task 8: Atualizar import em `main.py`

**Files:**
- Modify: `main.py:19`

- [ ] **Step 1: Substituir a linha de import**

Linha atual (linha 19):
```python
from wasp.telegram import _install_start_token_handler  # noqa: E402
```

Substituir por:
```python
from wasp.clients.telegram import _install_start_token_handler  # noqa: E402
```

- [ ] **Step 2: Verificar**

```bash
python -c "import main; print('OK')" 2>&1 | head -5
```
Esperado: pode dar erro por falta de `.env`, mas não deve dar `ImportError`.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "refactor(main): update telegram import to wasp.clients.telegram"
```

---

### Task 9: Atualizar `tests/test_telegram.py`

**Files:**
- Modify: `tests/test_telegram.py`

- [ ] **Step 1: Substituir todos os imports de `wasp.telegram`**

Há duas substituições a fazer:

**Substituição 1** — todas as ocorrências de `from wasp.telegram import _process_start_token`:
```python
from wasp.clients.telegram import _process_start_token
```

**Substituição 2** — todas as ocorrências de `from wasp.telegram import _install_start_token_handler`:
```python
from wasp.clients.telegram import _install_start_token_handler
```

**Substituição 3** — a linha `import wasp.telegram as telegram_mod`:
```python
import wasp.clients.telegram.webhook as telegram_mod
```

- [ ] **Step 2: Verificar que o arquivo ainda referencia os módulos certos**

```bash
grep -n "wasp.telegram\|wasp.clients.telegram" tests/test_telegram.py
```
Esperado: zero ocorrências de `wasp.telegram`, apenas `wasp.clients.telegram`.

- [ ] **Step 3: Rodar os testes de telegram**

```bash
pytest tests/test_telegram.py -v
```
Esperado: todos passam.

- [ ] **Step 4: Commit**

```bash
git add tests/test_telegram.py
git commit -m "test(telegram): update imports to wasp.clients.telegram"
```

---

### Task 10: Atualizar `tests/test_watcher.py`

**Files:**
- Modify: `tests/test_watcher.py`

Há cinco tipos de substituição:

- [ ] **Step 1: Substituir `import wasp.notifier as n` (linha 131)**

```python
import wasp.clients.telegram.notifier as n
```

- [ ] **Step 2: Substituir todas as ocorrências de `from wasp.notifier import RecordingNotifier`**

```python
from tests.notifiers import RecordingNotifier
```

- [ ] **Step 3: Substituir `from wasp.notifier import ConsoleNotifier`**

```python
from wasp.clients.local import ConsoleNotifier
```

- [ ] **Step 4: Substituir `from wasp.notifier import TelegramNotifier`**

```python
from wasp.clients.telegram import TelegramNotifier
```

- [ ] **Step 5: Atualizar o logger no test_console_notifier_logs_message**

Linha atual:
```python
caplog.set_level(logging.INFO, logger="wasp.notifier")
```

Substituir por:
```python
caplog.set_level(logging.INFO, logger="wasp.clients.local.notifier")
```

- [ ] **Step 6: Verificar que não há mais referências antigas**

```bash
grep -n "wasp.notifier" tests/test_watcher.py
```
Esperado: nenhuma ocorrência.

- [ ] **Step 7: Rodar os testes de watcher**

```bash
pytest tests/test_watcher.py -v
```
Esperado: todos passam.

- [ ] **Step 8: Commit**

```bash
git add tests/test_watcher.py
git commit -m "test(watcher): update imports to wasp.clients"
```

---

### Task 11: Atualizar `tests/e2e/conftest.py`

**Files:**
- Modify: `tests/e2e/conftest.py:208`

- [ ] **Step 1: Substituir o import**

Linha atual (linha 208):
```python
from wasp.notifier import RecordingNotifier
```

Substituir por:
```python
from tests.notifiers import RecordingNotifier
```

- [ ] **Step 2: Verificar**

```bash
grep -n "wasp.notifier" tests/e2e/conftest.py
```
Esperado: nenhuma ocorrência.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/conftest.py
git commit -m "test(e2e): update RecordingNotifier import to tests.notifiers"
```

---

### Task 12: Atualizar `tests/conftest.py` — sys.modules.pop

**Files:**
- Modify: `tests/conftest.py`

Há **dois** blocos idênticos (setup e teardown do fixture) que precisam ser atualizados.

- [ ] **Step 1: Em cada bloco, substituir `"wasp.telegram",` pelo bloco de módulos novos**

Nos dois blocos (linhas ~50-64 e ~80-96), substituir:
```python
        "wasp.telegram",
```
por:
```python
        "wasp.clients",
        "wasp.clients.telegram",
        "wasp.clients.telegram.notifier",
        "wasp.clients.telegram.webhook",
        "wasp.clients.local",
        "wasp.clients.local.notifier",
```

- [ ] **Step 2: Verificar que não há mais `wasp.telegram` nem `wasp.notifier` nos blocos**

```bash
grep -n "wasp.telegram\|wasp.notifier" tests/conftest.py
```
Esperado: nenhuma ocorrência.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: update sys.modules.pop to wasp.clients in conftest"
```

---

### Task 13: Rodar suite completa com arquivos antigos ainda presentes

- [ ] **Step 1: Rodar make test**

```bash
make test
```
Esperado: 100% coverage, todos os testes passam.

Se algum teste falhar, corrija o import correspondente antes de prosseguir.

---

### Task 14: Deletar arquivos antigos e verificar

**Files:**
- Delete: `wasp/notifier.py`
- Delete: `wasp/telegram.py`

- [ ] **Step 1: Deletar os arquivos**

```bash
git rm wasp/notifier.py wasp/telegram.py
```

- [ ] **Step 2: Rodar make test novamente**

```bash
make test
```
Esperado: 100% coverage, todos os testes passam.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: delete wasp/notifier.py and wasp/telegram.py"
```

---

### Task 15: Atualizar CLAUDE.md com estrutura de pacotes preferida

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Adicionar nova seção sobre estrutura de clients/**

Adicionar após a seção `## 14. Notifier abstraction` (ou no final do arquivo, antes de seções não existentes):

```markdown
## 22. Estrutura de pacotes — `wasp/clients/`

Código específico de um canal de notificação ou integração externa vive em `wasp/clients/<canal>/`:

```
wasp/clients/
  __init__.py          ← Notifier Protocol
  telegram/
    __init__.py        ← re-exports públicos
    notifier.py        ← implementação do Notifier
    webhook.py         ← integração específica (ex: webhook auth)
  local/
    __init__.py
    notifier.py
```

- `wasp/clients/__init__.py` define apenas o `Notifier` Protocol.
- Cada subpacote expõe sua API pública via `__init__.py`.
- `RecordingNotifier` (test double) fica em `tests/notifiers.py`, não em `wasp/clients/`.
- Ao adicionar novo canal (Discord, Slack), criar `wasp/clients/<canal>/` seguindo o mesmo padrão.
```

- [ ] **Step 2: Verificar que a seção foi adicionada**

```bash
grep -n "wasp/clients" CLAUDE.md | tail -5
```
Esperado: linhas referenciando a nova seção.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md): add clients/ package structure guideline"
```

---

### Task 16: Validação final

- [ ] **Step 1: Formatar**

```bash
make format
```

- [ ] **Step 2: Commitar formatação se houver mudanças**

```bash
git add -p
git commit -m "style: apply ruff format after clients refactor"
```
(pular se não houver mudanças)

- [ ] **Step 3: make test (cobertura 100%)**

```bash
make test
```
Esperado: todos os testes passam, 100% coverage.

- [ ] **Step 4: make e2e-with-debug**

```bash
make e2e-with-debug
```
Esperado: fluxo completo de provisionamento passa (turn-1, turn-2, watcher, notificação).

- [ ] **Step 5: make gitops-up**

```bash
make gitops-up
```
Esperado: cluster GitOps sobe corretamente.

- [ ] **Step 6: make local-chat**

```bash
make local-chat
```
Esperado: callback do notifier aparece no terminal (verificar linha `[NOTIFIER chat_id=...]`).

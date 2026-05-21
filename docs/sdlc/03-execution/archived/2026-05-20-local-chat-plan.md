# Local chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Habilitar conversa interativa com o `wasp-agent` via `curl`, com notificação async no stdout do servidor, como evolução do smoke test Telegram.

**Architecture:** Reusa `POST /agents/wasp-agent/runs` do `AgentOS` (sem auth em dev local). Adiciona `ConsoleNotifier`, seleção de notifier por env var (`NOTIFIER`), aceita `session_id` no formato `local:<agent>:<chat_id>` e fornece script bash + target Makefile para o usuário.

**Tech Stack:** Python 3.14, agno, pytest, bash, jq, curl.

**Spec:** `docs/sdlc/02-design/2026-05-20-local-chat.md`

---

## File Structure

**Create:**
- `scripts/local-chat` — bash wrapper sobre `curl`, persiste `session_id`
- `scripts/local-chat-scenario` — bash, roda roteiro scripted invocando `local-chat`
- `docs/runbooks/local-chat.md` — runbook manual

**Modify:**
- `wasp/notifier.py` — adiciona `ConsoleNotifier`
- `wasp/watcher.py` — `extract_chat_id` aceita prefixo `local:`
- `wasp/provision.py` — `_select_notifier()` factory + uso no spawn do watcher
- `tests/test_watcher.py` — teste para `local:`
- `tests/test_provision.py` — testes para `_select_notifier` e caminho console
- `Makefile` — target `local-chat`
- `docs/runbooks/validation.md` — adiciona Path D
- `HANDOFF.md` — atualiza progresso e move spec para Implemented
- `.env.example` — comenta `NOTIFIER` e `WASP_AGENT_URL`

---

### Task 1: `ConsoleNotifier` em `wasp/notifier.py`

**Files:**
- Modify: `wasp/notifier.py`
- Test: `tests/test_watcher.py`

- [ ] **Step 1: Write failing tests**

Append ao final de `tests/test_watcher.py`:

```python
async def test_console_notifier_logs_message(caplog):
    import logging
    from tools.notifier import ConsoleNotifier

    caplog.set_level(logging.INFO, logger="tools.notifier")
    notifier = ConsoleNotifier()
    await notifier.send("abc123", "Plataforma test está pronta.")

    assert any(
        "[NOTIFIER chat_id=abc123]" in r.message and "Plataforma test está pronta." in r.message
        for r in caplog.records
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_watcher.py::test_console_notifier_logs_message -v --no-cov
```

Expected: FAIL com `ImportError: cannot import name 'ConsoleNotifier'`.

- [ ] **Step 3: Implement `ConsoleNotifier`**

Em `wasp/notifier.py`, no topo (após `import asyncio`):

```python
import logging
```

E ao final do arquivo:

```python
log = logging.getLogger(__name__)


class ConsoleNotifier:
    async def send(self, chat_id: str, text: str) -> None:
        log.info("[NOTIFIER chat_id=%s] %s", chat_id, text)
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest --cov=. --cov-report=term-missing
```

Expected: PASS, cobertura 100%.

- [ ] **Step 5: Lint**

```bash
uv run ruff check .
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add wasp/notifier.py tests/test_watcher.py
git commit -m "feat(notifier): add ConsoleNotifier for local dev"
```

---

### Task 2: `extract_chat_id` aceita prefixo `local:`

**Files:**
- Modify: `wasp/watcher.py:23`
- Test: `tests/test_watcher.py`

- [ ] **Step 1: Write failing test**

Append a `tests/test_watcher.py`:

```python
def test_extract_chat_id_from_local_session():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    assert extract_chat_id(FakeCtx()) == "abc12345"


def test_extract_chat_id_from_local_session_with_suffix():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345:8ec68b0f"

    assert extract_chat_id(FakeCtx()) == "abc12345"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_watcher.py::test_extract_chat_id_from_local_session -v --no-cov
```

Expected: FAIL (retorna `None`).

- [ ] **Step 3: Update `extract_chat_id`**

Em `wasp/watcher.py`, substitua a linha 23:

```python
    if len(parts) >= 3 and parts[0] == "tg":
```

por:

```python
    if len(parts) >= 3 and parts[0] in ("tg", "local"):
```

E atualize o comentário acima:

```python
    # session_id: <prefix>:<agent-name>:<chat_id>[:<message_short_id>]
    # prefix: "tg" (Telegram) | "local" (curl/CLI)
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest --cov=. --cov-report=term-missing
```

Expected: PASS, cobertura 100%.

- [ ] **Step 5: Lint**

```bash
uv run ruff check .
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add wasp/watcher.py tests/test_watcher.py
git commit -m "feat(watcher): accept 'local:' prefix in extract_chat_id"
```

---

### Task 3: `_select_notifier` factory em `wasp/provision.py`

**Files:**
- Modify: `wasp/provision.py`
- Test: `tests/test_provision.py`

- [ ] **Step 1: Write failing tests**

Append a `tests/test_provision.py`:

```python
def test_select_notifier_console_when_env_explicit(monkeypatch):
    from tools.provision import _select_notifier
    from tools.notifier import ConsoleNotifier

    monkeypatch.setenv("NOTIFIER", "console")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")  # ignored

    notifier = _select_notifier()
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_telegram_when_env_explicit(monkeypatch):
    from tools.provision import _select_notifier
    from tools.notifier import TelegramNotifier

    monkeypatch.setenv("NOTIFIER", "telegram")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_default_telegram_when_token(monkeypatch):
    from tools.provision import _select_notifier
    from tools.notifier import TelegramNotifier

    monkeypatch.delenv("NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_default_console_without_token(monkeypatch):
    from tools.provision import _select_notifier
    from tools.notifier import ConsoleNotifier

    monkeypatch.delenv("NOTIFIER", raising=False)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    notifier = _select_notifier()
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_returns_none_when_telegram_without_token(monkeypatch):
    from tools.provision import _select_notifier

    monkeypatch.setenv("NOTIFIER", "telegram")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    assert _select_notifier() is None


def test_provision_spawns_watcher_with_console_notifier(monkeypatch):
    from unittest.mock import MagicMock, patch
    from tools.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setattr("tools.provision.PyGithubClient", mock_client_cls)

    mock_thread = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread)

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    with patch("tools.provision.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(
            name="wp2", domain="wasp.silvios.me", regions=["us-east-1"], run_context=FakeCtx(),
        )

    mock_thread_cls.assert_called_once()
    mock_thread.start.assert_called_once()
    assert result["status"] == "provisioning"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_provision.py -v --no-cov -k "select_notifier or console_notifier"
```

Expected: FAIL com `ImportError: cannot import name '_select_notifier'`.

- [ ] **Step 3: Implement `_select_notifier` and refactor spawn**

Em `wasp/provision.py`, substituir o import:

```python
from tools.notifier import TelegramNotifier
```

por:

```python
from tools.notifier import ConsoleNotifier, Notifier, TelegramNotifier
```

Adicionar abaixo dos imports:

```python
def _select_notifier() -> Notifier | None:
    kind = os.getenv("NOTIFIER")
    token = os.getenv("TELEGRAM_TOKEN")
    if kind is None:
        kind = "telegram" if token else "console"
    if kind == "console":
        return ConsoleNotifier()
    if kind == "telegram":
        return TelegramNotifier(token=token) if token else None
    return None
```

Substituir o bloco em `provision_platform_instance` (linhas ~98-108):

```python
chat_id = extract_chat_id(run_context)
token = os.getenv("TELEGRAM_TOKEN")
if chat_id and token:
    current_span.set_attribute("watcher.spawned", True)
    parent_span_ctx = current_span.get_span_context()
    notifier = TelegramNotifier(token=token)
    def _run_watcher():
        asyncio.run(watch_platform(name, chat_id, notifier, parent_span_ctx))

    threading.Thread(target=_run_watcher, daemon=True).start()
    log.info("Watcher spawned for %s (chat_id=%s)", name, chat_id)
```

por:

```python
chat_id = extract_chat_id(run_context)
notifier = _select_notifier()
if chat_id and notifier is not None:
    current_span.set_attribute("watcher.spawned", True)
    parent_span_ctx = current_span.get_span_context()
    def _run_watcher():
        asyncio.run(watch_platform(name, chat_id, notifier, parent_span_ctx))

    threading.Thread(target=_run_watcher, daemon=True).start()
    log.info("Watcher spawned for %s (chat_id=%s)", name, chat_id)
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest --cov=. --cov-report=term-missing
```

Expected: PASS, cobertura 100%.

- [ ] **Step 5: Lint**

```bash
uv run ruff check .
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add wasp/provision.py tests/test_provision.py
git commit -m "feat(provision): NOTIFIER env var selects console or telegram"
```

---

### Task 4: `scripts/local-chat`

**Files:**
- Create: `scripts/local-chat`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
set -e

readonly SESSION_FILE=".wasp-cli/session"
readonly WASP_AGENT_URL="${WASP_AGENT_URL:-http://localhost:7777}"
readonly WASP_AGENT_ID="${WASP_AGENT_ID:-wasp-agent}"

usage() {
  cat <<'EOF'
local-chat — wrapper sobre POST /agents/<id>/runs

Usage:
  local-chat MESSAGE            send message, print agent reply
  local-chat --new-session      generate a new session_id (local:<agent>:<uuid8>)
  local-chat --session          print current session_id
  local-chat --help             this help

Env:
  WASP_AGENT_URL   default http://localhost:7777
  WASP_AGENT_ID    default wasp-agent

Session_id persisted in .wasp-cli/session (cwd-local).
EOF
}

ensure_session() {
  if [[ ! -f "${SESSION_FILE}" ]]; then
    new_session
  fi
  cat "${SESSION_FILE}"
}

new_session() {
  local chat_id session_id
  chat_id="$(uuidgen | tr -d '-' | cut -c1-8)"
  session_id="local:${WASP_AGENT_ID}:${chat_id}"
  mkdir -p "$(dirname "${SESSION_FILE}")"
  echo "${session_id}" > "${SESSION_FILE}"
  echo "${session_id}"
}

send_message() {
  local message="${1?}" session_id
  session_id="$(ensure_session)"
  curl --silent --show-error --fail \
    "${WASP_AGENT_URL}/agents/${WASP_AGENT_ID}/runs" \
    --form "message=${message}" \
    --form "session_id=${session_id}" \
    --form "stream=false" \
    | jq -r '.content'
}

case "${1:-}" in
  --help|-h|"")
    usage
    ;;
  --new-session)
    new_session
    ;;
  --session)
    ensure_session
    ;;
  --*)
    echo "Unknown option: $1" >&2
    usage >&2
    exit 1
    ;;
  *)
    send_message "$1"
    ;;
esac
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/local-chat
```

- [ ] **Step 3: Smoke test manually**

In one terminal:

```bash
make run
```

In another:

```bash
scripts/local-chat --new-session
# expect: local:wasp-agent:<8 hex chars>
scripts/local-chat "oi"
# expect: a text reply (any greeting/clarification from the LLM)
```

If output looks right, proceed. Stop `make run` (Ctrl+C).

- [ ] **Step 4: Add `.wasp-cli/` to `.gitignore`**

Check current `.gitignore`:

```bash
cat .gitignore
```

If `.wasp-cli/` is not present, append:

```bash
echo "" >> .gitignore
echo "# local-chat session state" >> .gitignore
echo ".wasp-cli/" >> .gitignore
```

- [ ] **Step 5: Commit**

```bash
git add scripts/local-chat .gitignore
git commit -m "feat(scripts): add local-chat curl wrapper for agent runs"
```

---

### Task 5: `scripts/local-chat-scenario` + Makefile target

**Files:**
- Create: `scripts/local-chat-scenario`
- Modify: `Makefile`

- [ ] **Step 1: Write the roteiro script**

```bash
#!/usr/bin/env bash
# Replays the Telegram smoke roteiro via local-chat: greet → memory → request → confirm.
# No asserts on LLM content (non-deterministic) — only that each request returned 200.
set -e

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATH="${SCRIPT_DIR}:${PATH}"
export PATH

step() {
  local label="${1?}" message="${2?}"
  echo
  echo "─── ${label} ───"
  echo "> ${message}"
  echo
  local_chat_reply="$(local-chat "${message}")"
  echo "${local_chat_reply}"
}

echo "session: $(local-chat --new-session)"
step "1/5 greet" "oi"
step "2/5 memory write" "Meu nome é João."
step "3/5 memory recall" "Qual é o meu nome?"
step "4/5 request" "Crie uma plataforma chamada test-smoke na região us-east-1."
step "5/5 confirm" "Sim, confirma."

echo
echo "Roteiro concluído. Veja o stdout do servidor (make run) para o ConsoleNotifier."
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/local-chat-scenario
```

- [ ] **Step 3: Add Makefile target**

Em `Makefile`, na linha `.PHONY:`, adicionar `local-chat`:

```makefile
.PHONY: run test e2e k3d-up k3d-down build smoke smoke-prometheus local-chat
```

E adicionar target ao final:

```makefile
local-chat:
	scripts/local-chat-scenario
```

- [ ] **Step 4: Smoke test**

Terminal 1:

```bash
make run
```

Terminal 2:

```bash
make local-chat
```

Expected: imprime 5 turnos, sem erro, último turno é a resposta do agent à confirmação. Sem cluster/GitHub configurados, o passo 5 vai retornar erro do tool (`Provisioning failed.`) — isso é esperado para o smoke sem infra.

- [ ] **Step 5: Commit**

```bash
git add scripts/local-chat-scenario Makefile
git commit -m "feat(make): add 'local-chat' target running scripted roteiro"
```

---

### Task 6: Runbook `docs/runbooks/local-chat.md` + update `validation.md`

**Files:**
- Create: `docs/runbooks/local-chat.md`
- Modify: `docs/runbooks/validation.md`
- Modify: `.env.example`

- [ ] **Step 1: Write `docs/runbooks/local-chat.md`**

```markdown
# Local chat — interagir com o agent via curl

Caminho de validação manual sem Telegram. Evolução do smoke Telegram (`validation.md` path B). Útil para iterar sobre `INSTRUCTIONS`, memória de sessão e ciclo de provisionamento.

## Pré-requisitos

- `curl`, `jq`, `uuidgen` no PATH.
- Para o happy path completo (provision + notificação async): cluster com ArgoCD + Crossplane + Composition, `GH_PAT` válido. Ver apêndice de `validation.md`.

Para validação só do LLM (sem provisionar), basta o agent rodando — recuse a confirmação no passo de criação.

## Setup

Sem Telegram:

```bash
unset TELEGRAM_TOKEN
make run
```

O log do servidor inicia com o `ConsoleNotifier` selecionado (default sem `TELEGRAM_TOKEN`). Para forçar, exporte `NOTIFIER=console`.

## Uso manual

Em outro terminal:

```bash
scripts/local-chat --new-session
scripts/local-chat "oi"
scripts/local-chat "Meu nome é João."
scripts/local-chat "Qual é o meu nome?"
scripts/local-chat "Crie uma plataforma chamada wp-demo na região us-east-1."
scripts/local-chat "Sim, confirma."
```

Quando o `Platform` ficar `Ready=True`, o `ConsoleNotifier` escreve no log do `make run`:

```
[NOTIFIER chat_id=abc12345] Plataforma 'wp-demo' está pronta.
- us-east-1: https://gateway.us-east-1.wp-demo.wasp.silvios.me
```

## Roteiro scripted

```bash
make local-chat
```

Roda os 5 turnos automaticamente. Sem cluster configurado, o passo 5 retorna erro do tool — esperado.

## Estado da sessão

`session_id` persiste em `.wasp-cli/session` (cwd-local, ignorado pelo git). Para zerar:

```bash
scripts/local-chat --new-session
```

## Variáveis

| Var | Default | Observação |
|---|---|---|
| `NOTIFIER` | auto (`telegram` se `TELEGRAM_TOKEN`, senão `console`) | Força a escolha |
| `WASP_AGENT_URL` | `http://localhost:7777` | URL base do servidor |
| `WASP_AGENT_ID` | `wasp-agent` | ID do agent no AgentOS |
```

- [ ] **Step 2: Update `docs/runbooks/validation.md`**

Após a seção "C. Validar Prometheus", insira:

```markdown
---

## D. Local chat — manual, **sem Telegram**

Equivalente ao path B (smoke Telegram), mas usando `curl` / `scripts/local-chat`. Ver [`local-chat.md`](local-chat.md).

Útil para iteração rápida em system prompt, memória de sessão e fluxo de confirmação sem montar ngrok + bot.

```bash
unset TELEGRAM_TOKEN
make run

# em outro terminal
make local-chat
```

Para o happy-path com notificação `Ready` (passos 4-5 do roteiro chegam a `provision_platform_instance` rodando de verdade), o setup de infra é o do apêndice abaixo.
```

- [ ] **Step 3: Update `.env.example`**

Adicionar ao final:

```bash

# Local chat (path D em validation.md) — sem Telegram.
# Default: 'telegram' se TELEGRAM_TOKEN estiver setado, senão 'console'.
# NOTIFIER=console

# WASP_AGENT_URL=http://localhost:7777
# WASP_AGENT_ID=wasp-agent
```

- [ ] **Step 4: Commit**

```bash
git add docs/runbooks/local-chat.md docs/runbooks/validation.md .env.example
git commit -m "docs(runbooks): add local-chat path D"
```

---

### Task 7: HANDOFF.md update + spec status

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/sdlc/02-design/2026-05-20-local-chat.md`

- [ ] **Step 1: Mark spec as Implemented**

Em `docs/sdlc/02-design/2026-05-20-local-chat.md`, mudar:

```
**Status:** Draft
```

para:

```
**Status:** Implemented
```

- [ ] **Step 2: Update `HANDOFF.md`**

Na seção `## Current Progress`, adicionar um parágrafo após o existente:

```markdown
**Path D — Local chat** implementado em 2026-05-20. Conversa via `curl` sem Telegram (`make local-chat`, `scripts/local-chat`). Base para `waspctl` futura.
```

Na seção `## Next Steps` → `### 1. Smoke test Telegram (manual)`, adicionar uma alternativa:

```markdown
Alternativa rápida sem ngrok/bot: path D (`docs/runbooks/local-chat.md`).
```

- [ ] **Step 3: Verify tests still pass and lint clean**

```bash
uv run pytest --cov=. --cov-report=term-missing
uv run ruff check .
```

Expected: PASS, cobertura 100%, lint clean.

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md docs/sdlc/02-design/2026-05-20-local-chat.md
git commit -m "docs: mark local-chat spec Implemented and update HANDOFF"
```

Archive (move to `archived/` per CLAUDE.md §7) happens **after** merge to `main`, not in this plan.

---

## Self-Review

- **Spec coverage:** todos os 6 componentes do spec mapeados (ConsoleNotifier T1, NOTIFIER env T3, chat_id T2, script T4, target T5, runbook T6).
- **Verificação:** unit tests cobrem ConsoleNotifier, _select_notifier (5 casos), extract_chat_id local, watcher spawn com console. Cobertura 100% mantida ao final de T1-T3.
- **Out of scope respeitado:** sem CLI completa, sem asserts no LLM, sem GiteaClient runtime, sem auth.

---

## Done

Ao final, o usuário consegue:

```bash
unset TELEGRAM_TOKEN
make run    # terminal 1
make local-chat   # terminal 2 — ou interativo com scripts/local-chat "mensagem"
```

E ver o `[NOTIFIER ...]` quando o watcher detecta `Ready` (se a infra do apêndice de `validation.md` estiver pronta).
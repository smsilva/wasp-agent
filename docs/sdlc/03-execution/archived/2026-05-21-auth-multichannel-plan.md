# Autenticação multi-canal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar autenticação/autorização multi-canal no `wasp-agent` via mapeamento `(channel, channel_id) → user_id` interno, com onboarding por invite admin + deep link `/start <token>` no Telegram.

**Architecture:** Tabelas `auth_users`, `auth_identities`, `auth_invites` no mesmo `agent.db` (prefixo `auth_*`). Módulo `wasp/auth.py` com conexão `sqlite3` direta (não via agno). Verificação na tool `provision_platform_instance` (opção B do spec — opção A descartada após investigação do agno; ver Task 3). Handler de `/start <token>` registrado como rota Starlette antes do agno. CLI admin via scripts em `scripts/` + Make targets.

**Tech Stack:** Python 3.14, `sqlite3` stdlib, agno, pytest, bash.

**Spec:** `docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md`

---

## File Structure

**Create:**
- `wasp/auth.py` — módulo de auth (schema, queries, invite/redeem/revoke)
- `tests/test_auth.py` — unit tests, 100% coverage
- `scripts/admin-invite` — bash, gera invite
- `scripts/admin-revoke` — bash, revoga identity
- `scripts/admin-list` — bash, lista identities ativas
- `scripts/admin-bootstrap` — bash, cria o primeiro admin (só funciona com tabela vazia)
- `docs/runbooks/auth-admin.md` — runbook do operador

**Modify:**
- `wasp/provision.py` — guard `is_authorized(channel, channel_id)` no início de `provision_platform_instance`; span attribute `user.id`
- `main.py` — registra rota `/telegram/start` (ou hook similar) para consumir `/start <token>`; logging do `ConsoleNotifier` passa a usar `user.id` quando disponível
- `wasp/telemetry.py` — registra métrica Prometheus `wasp_auth_denied_total`
- `tests/test_provision.py` — testes do guard (autorizado / não autorizado / sem chat_id)
- `tests/test_main.py` — teste do handler `/start <token>`
- `tests/test_telemetry.py` — teste da métrica
- `Makefile` — targets `admin-invite`, `admin-revoke`, `admin-list`, `admin-bootstrap`
- `.env.example` — `WASP_AGENT_DB_FILE`, `WASP_AGENT_INVITE_TTL_HOURS`
- `docs/runbooks/validation.md` — nota sobre auth no path B (smoke Telegram)
- `HANDOFF.md` — progresso + status do spec

---

### Task 1: Schema + módulo `wasp/auth.py` (sem integração)

**Files:**
- Create: `wasp/auth.py`
- Create: `tests/test_auth.py`

API a implementar:

```python
def init_db(db_file: str) -> None: ...
def is_authorized(channel: str, channel_id: str, db_file: str | None = None) -> str | None: ...
def create_invite(display_name: str, created_by: str, channel: str | None = None,
                  channel_id: str | None = None, db_file: str | None = None) -> str: ...
def redeem_invite(token: str, channel: str, channel_id: str,
                  db_file: str | None = None) -> tuple[str, str] | None: ...  # (user_id, display_name) | None
def revoke(channel: str, channel_id: str, db_file: str | None = None) -> bool: ...
def list_identities(db_file: str | None = None) -> list[dict]: ...
def has_any_user(db_file: str | None = None) -> bool: ...
def create_user(display_name: str, db_file: str | None = None) -> str: ...  # usado só pelo bootstrap
def link_identity(user_id: str, channel: str, channel_id: str, db_file: str | None = None) -> None: ...
```

`db_file` default lido de `os.getenv("WASP_AGENT_DB_FILE", "agent.db")`. Conexão `sqlite3` por chamada (sem singleton — barato no agent.db local; revisitar se virar gargalo). `PRAGMA foreign_keys=ON` em cada conexão. `init_db` é idempotente (`CREATE TABLE IF NOT EXISTS`).

- [ ] **Step 1: Write failing tests**

Criar `tests/test_auth.py` cobrindo (mínimo 100% das linhas de `wasp/auth.py`):

- `init_db` cria as três tabelas (verificar via `sqlite_master`).
- `init_db` é idempotente.
- `is_authorized` retorna `None` para `(channel, channel_id)` desconhecido.
- `create_user` retorna UUID string e persiste.
- `link_identity` permite `is_authorized` retornar o `user_id`.
- `create_invite` retorna token URL-safe ≥ 40 chars, persiste com `expires_at = created_at + TTL`.
- `create_invite` lê TTL de `WASP_AGENT_INVITE_TTL_HOURS` (default 1).
- `redeem_invite` cria identity, marca `used_at`, retorna `(user_id, display_name)`.
- `redeem_invite` retorna `None` se token desconhecido.
- `redeem_invite` retorna `None` se token expirado.
- `redeem_invite` retorna `None` se token já consumido.
- `redeem_invite` com `channel` pré-vinculado: rejeita se canal diferente.
- `revoke` remove identity, mantém user, retorna `True`. Retorna `False` se não existir.
- `list_identities` retorna dicts com `channel`, `channel_id`, `user_id`, `display_name`, `linked_at`.
- `has_any_user` retorna `False` em DB vazio, `True` após `create_user`.

Use `tmp_path` para isolar `agent.db` por teste:

```python
@pytest.fixture
def db_file(tmp_path):
    return str(tmp_path / "agent.db")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_auth.py -v --no-cov
```

Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implement `wasp/auth.py`**

DDL conforme §4.2 do spec. `secrets.token_urlsafe(32)` para tokens. `uuid.uuid4().hex` para `user_id`. Timestamps `datetime.now(timezone.utc).isoformat()`.

- [ ] **Step 4: Run all tests + coverage**

```bash
uv run pytest --cov=. --cov-report=term-missing
```

Expected: PASS, cobertura 100% (incluindo `wasp/auth.py`).

- [ ] **Step 5: Lint**

```bash
uv run ruff check .
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add wasp/auth.py tests/test_auth.py
git commit -m "feat(auth): add multi-channel identity + invite module"
```

---

### Task 2: Guard em `provision_platform_instance`

**Files:**
- Modify: `wasp/provision.py`
- Modify: `tests/test_provision.py`

A tool é o ponto de execução de qualquer ação privilegiada. Guard aqui bloqueia o efeito colateral mesmo se o webhook não filtrar (defense-in-depth). Não economiza tokens LLM — isso fica para uma iteração futura (ver §5.2 do spec, opção A).

**Política por canal:** o canal `local` (curl/local-chat) é tratado como **trusted** — não tem identidade verificável (cliente HTTP escolhe `session_id` arbitrário). O boundary de segurança do `local` é a rede (endpoint AgentOS deve ouvir só `127.0.0.1` em produção). Allowlist em `local` seria falha de segurança. Canais com identidade nativa (`tg`, futuros `discord`/`slack`) requerem auth. Ver `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` para a evolução do `local`/`cli` com identidade real.

- [ ] **Step 1: Write failing tests**

Append a `tests/test_provision.py`:

```python
def test_provision_returns_unauthorized_when_tg_chat_id_unknown(monkeypatch):
    from wasp.provision import provision_platform_instance

    monkeypatch.setattr("wasp.auth.is_authorized", lambda channel, channel_id: None)

    class FakeCtx:
        session_id = "tg:wasp-agent:999999"

    result = provision_platform_instance(
        name="x", domain="d", regions=["us-east-1"], run_context=FakeCtx(),
    )
    assert result == {"status": "unauthorized", "message": "Acesso negado."}


def test_provision_skips_auth_for_local_channel(monkeypatch):
    """local channel é trusted — não tem identidade verificável, boundary é a rede."""
    from wasp.provision import provision_platform_instance

    is_authorized_called = []
    monkeypatch.setattr("wasp.auth.is_authorized",
                        lambda c, i: is_authorized_called.append((c, i)) or None)
    # ... mock PyGithubClient + threading.Thread como nos testes existentes

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    result = provision_platform_instance(
        name="x", domain="d", regions=["us-east-1"], run_context=FakeCtx(),
    )
    assert result["status"] == "provisioning"
    assert is_authorized_called == []  # nunca foi chamado


def test_provision_proceeds_when_tg_authorized(monkeypatch):
    # ... reaproveitar mock existente do PyGithubClient + verificar que a thread é spawnada
```

Ajustar os testes existentes de `provision_platform_instance` que usam `session_id = "tg:..."` para mockar `wasp.auth.is_authorized` retornando um `user_id` fake (`"user-abc"`), senão eles passam a falhar com unauthorized. Testes com `session_id = "local:..."` continuam funcionando sem mock de auth.

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_provision.py -v --no-cov
```

- [ ] **Step 3: Implement guard**

No topo de `provision_platform_instance`:

```python
from wasp import auth
from wasp.watcher import extract_channel  # já existe

TRUSTED_CHANNELS = {"local"}  # boundary é a rede, não a allowlist

channel = extract_channel(run_context)
chat_id = extract_chat_id(run_context)

if channel in TRUSTED_CHANNELS:
    user_id = f"local-operator"  # placeholder estável para spans
else:
    user_id = auth.is_authorized(channel, chat_id) if (channel and chat_id) else None
    if user_id is None:
        log.warning("auth denied: channel=%s channel_id=%s", channel, chat_id)
        telemetry.auth_denied(channel=channel or "unknown", reason="unknown_identity")
        return {"status": "unauthorized", "message": "Acesso negado."}

current_span.set_attribute("user.id", user_id)
current_span.set_attribute("auth.channel", channel or "unknown")
```

A chamada a `telemetry.auth_denied` será implementada na Task 6. Por ora, importar de `wasp.telemetry` (pode ficar como stub se ordenar Task 6 depois).

- [ ] **Step 4: Run all tests**

```bash
uv run pytest --cov=. --cov-report=term-missing
```

Expected: PASS, cobertura 100%.

- [ ] **Step 5: Lint**

```bash
uv run ruff check .
```

- [ ] **Step 6: Commit**

```bash
git add wasp/provision.py tests/test_provision.py
git commit -m "feat(provision): deny tool call for unauthorized identities"
```

---

### Task 3: Handler de `/start <token>` no Telegram

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

**Investigação prévia (gate da task):** confirmar como o `agno.os.interfaces.telegram.Telegram` expõe handlers de comando. Se permitir registrar handler custom para `/start`, usar isso. Se não, fallback: rota Starlette `POST /telegram/webhook-intercept` que processa antes de delegar ao agno — opção mais invasiva.

Reportar a decisão no commit message ("agno expõe X, escolhido Y").

- [ ] **Step 1: Investigate agno Telegram interface**

```bash
uv run python -c "from agno.os.interfaces.telegram import Telegram; import inspect; print(inspect.getsourcefile(Telegram))"
```

Ler o arquivo. Identificar o ponto de entrada (`receive_message`, `dispatch`, ou similar) e se há hook para `/start`.

Se a interface for opaca, considerar: registrar handler diretamente via `python-telegram-bot` Application já criada pelo agno. Documentar achados em uma nota curta no commit message.

- [ ] **Step 2: Write failing test**

Em `tests/test_main.py`, escrever teste que simula um update Telegram com texto `/start ABC123` para um `chat_id` que não está em `auth_identities`, e verifica:
1. `auth.redeem_invite("ABC123", "tg", "<chat_id>")` é chamado.
2. Resposta enviada ao usuário é a mensagem de boas-vindas (se redeem OK) ou a genérica de "link inválido" (se redeem retornou `None`).
3. O agno **não** processa essa mensagem como um turno normal.

Estratégia: mockar `wasp.auth.redeem_invite` e o método de send do bot Telegram. Verificar chamadas.

- [ ] **Step 3: Implement handler**

Conforme achados da Step 1. Esboço (assume registro direto no Application):

```python
async def _telegram_start_handler(update, context):
    from wasp import auth

    chat_id = str(update.effective_user.id)
    args = context.args  # lista após /start

    if not args:
        # /start sem token: tratar como mensagem normal — deixa o agno responder
        # OU: se o user não está autorizado, ignorar silenciosamente
        if auth.is_authorized("tg", chat_id) is None:
            return  # silent ignore
        # autorizado: deixa fluir para o agno (não fazer nada aqui)
        return

    token = args[0]
    result = auth.redeem_invite(token, "tg", chat_id)
    if result is None:
        await update.effective_message.reply_text(
            "Link inválido ou expirado. Solicite um novo ao administrador."
        )
        return

    user_id, display_name = result
    await update.effective_message.reply_text(
        f"Bem-vindo, {display_name}. Você está autorizado a usar o wasp-agent."
    )
```

Registrar o handler **antes** que o agno tenha chance de processar `/start` como mensagem normal. Se a integração agno não permitir, ajustar.

- [ ] **Step 4: Run all tests**

```bash
uv run pytest --cov=. --cov-report=term-missing
```

- [ ] **Step 5: Lint**

```bash
uv run ruff check .
```

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat(telegram): handle /start <token> deep link for onboarding"
```

---

### Task 4: CLI admin — `scripts/admin-invite`, `admin-revoke`, `admin-list`

**Files:**
- Create: `scripts/admin-invite`
- Create: `scripts/admin-revoke`
- Create: `scripts/admin-list`
- Modify: `Makefile`

Scripts chamam um helper Python via `uv run python -c "..."` ou via módulo `python -m wasp.auth_cli` (decidir durante implementação — preferir módulo se virar mais de 5 linhas inline).

- [ ] **Step 1: Write `scripts/admin-invite`**

```bash
#!/usr/bin/env bash
set -e

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATH="${SCRIPT_DIR}:${PATH}"
export PATH

name="${1?usage: admin-invite NAME [CHANNEL]}"
channel="${2:-}"

bot_name="${TELEGRAM_BOT_USERNAME?TELEGRAM_BOT_USERNAME must be set}"

token=$(uv run python -m wasp.auth_cli invite \
  --name "${name}" \
  --created-by "admin" \
  ${channel:+--channel "${channel}"})

echo "Token: ${token}"
echo "Link:  https://t.me/${bot_name}?start=${token}"
```

- [ ] **Step 2: Write `scripts/admin-revoke`**

```bash
#!/usr/bin/env bash
set -e

channel="${1?usage: admin-revoke CHANNEL CHANNEL_ID}"
channel_id="${2?usage: admin-revoke CHANNEL CHANNEL_ID}"

uv run python -m wasp.auth_cli revoke \
  --channel "${channel}" \
  --channel-id "${channel_id}"
```

- [ ] **Step 3: Write `scripts/admin-list`**

```bash
#!/usr/bin/env bash
set -e

uv run python -m wasp.auth_cli list
```

- [ ] **Step 4: Implement `wasp/auth_cli.py`**

`argparse` subcommands (`invite`, `revoke`, `list`, `bootstrap`). Chama funções de `wasp.auth`. Print apenas o que o operador precisa ver (token, tabela formatada).

Adicionar testes mínimos em `tests/test_auth_cli.py` (ou estender `test_auth.py`) chamando `main()` com `sys.argv` patcheado e capturando stdout via `capsys`.

- [ ] **Step 5: Make scripts executable**

```bash
chmod +x scripts/admin-invite scripts/admin-revoke scripts/admin-list
```

- [ ] **Step 6: Add Makefile targets**

```makefile
.PHONY: ... admin-invite admin-revoke admin-list admin-bootstrap

admin-invite:
	@scripts/admin-invite "$(NAME)" $(CHANNEL)

admin-revoke:
	@scripts/admin-revoke $(CHANNEL) $(ID)

admin-list:
	@scripts/admin-list
```

- [ ] **Step 7: Run all tests + lint**

```bash
uv run pytest --cov=. --cov-report=term-missing
uv run ruff check .
```

- [ ] **Step 8: Commit**

```bash
git add wasp/auth_cli.py scripts/admin-invite scripts/admin-revoke scripts/admin-list Makefile tests/test_auth*.py
git commit -m "feat(scripts): add admin CLI for invite/revoke/list"
```

---

### Task 5: Bootstrap do primeiro admin

**Files:**
- Create: `scripts/admin-bootstrap`
- Modify: `Makefile`
- Modify: `wasp/auth_cli.py` (subcomando `bootstrap`)

Bootstrap só roda em DB vazio (`has_any_user() == False`). Cria o primeiro usuário **já vinculado** à identidade do admin no canal — pulando o fluxo de invite, porque não há quem emita.

- [ ] **Step 1: Write failing test**

Append a `tests/test_auth.py` (ou `test_auth_cli.py`):

```python
def test_bootstrap_creates_first_user_when_db_empty(db_file, monkeypatch):
    from wasp import auth

    user_id = auth.bootstrap_admin("Silvio", "tg", "12345678", db_file=db_file)
    assert user_id
    assert auth.is_authorized("tg", "12345678", db_file=db_file) == user_id


def test_bootstrap_fails_when_db_not_empty(db_file):
    from wasp import auth
    auth.create_user("First", db_file=db_file)
    with pytest.raises(RuntimeError, match="not empty"):
        auth.bootstrap_admin("Silvio", "tg", "12345678", db_file=db_file)
```

- [ ] **Step 2: Implement `auth.bootstrap_admin`**

```python
def bootstrap_admin(display_name: str, channel: str, channel_id: str,
                    db_file: str | None = None) -> str:
    if has_any_user(db_file=db_file):
        raise RuntimeError("auth tables not empty — bootstrap refused")
    user_id = create_user(display_name, db_file=db_file)
    link_identity(user_id, channel, channel_id, db_file=db_file)
    return user_id
```

- [ ] **Step 3: Write `scripts/admin-bootstrap`**

```bash
#!/usr/bin/env bash
set -e

name="${1?usage: admin-bootstrap NAME CHANNEL CHANNEL_ID}"
channel="${2?usage: admin-bootstrap NAME CHANNEL CHANNEL_ID}"
channel_id="${3?usage: admin-bootstrap NAME CHANNEL CHANNEL_ID}"

uv run python -m wasp.auth_cli bootstrap \
  --name "${name}" \
  --channel "${channel}" \
  --channel-id "${channel_id}"
```

```bash
chmod +x scripts/admin-bootstrap
```

- [ ] **Step 4: Add Makefile target**

```makefile
admin-bootstrap:
	@scripts/admin-bootstrap "$(NAME)" $(CHANNEL) $(ID)
```

- [ ] **Step 5: Run all tests + lint**

```bash
uv run pytest --cov=. --cov-report=term-missing
uv run ruff check .
```

- [ ] **Step 6: Commit**

```bash
git add wasp/auth.py wasp/auth_cli.py scripts/admin-bootstrap Makefile tests/test_auth*.py
git commit -m "feat(auth): bootstrap first admin via offline CLI"
```

---

### Task 6: Métrica Prometheus + span attributes

**Files:**
- Modify: `wasp/telemetry.py`
- Modify: `wasp/provision.py` (já chamou `telemetry.auth_denied` na Task 2)
- Modify: `tests/test_telemetry.py`
- Modify: `tests/test_provision.py`

- [ ] **Step 1: Write failing test**

Em `tests/test_telemetry.py`:

```python
def test_auth_denied_counter_increments():
    from wasp.telemetry import auth_denied, _auth_denied_counter

    before = _auth_denied_counter.labels(channel="tg", reason="unknown_identity")._value.get()
    auth_denied(channel="tg", reason="unknown_identity")
    after = _auth_denied_counter.labels(channel="tg", reason="unknown_identity")._value.get()
    assert after == before + 1
```

- [ ] **Step 2: Implement**

Em `wasp/telemetry.py`:

```python
from prometheus_client import Counter

_auth_denied_counter = Counter(
    "wasp_auth_denied_total",
    "Total auth denial events",
    ["channel", "reason"],
    registry=_prometheus_registry,
)


def auth_denied(*, channel: str, reason: str) -> None:
    _auth_denied_counter.labels(channel=channel, reason=reason).inc()
```

- [ ] **Step 3: Verify span attributes**

`current_span.set_attribute("user.id", user_id)` e `current_span.set_attribute("auth.channel", channel)` já foram adicionados na Task 2. Estender `tests/test_provision.py` para verificar via mock do span:

```python
def test_provision_sets_user_id_span_attribute(monkeypatch, ...):
    captured = {}
    def fake_set(name, value):
        captured[name] = value
    # ...mockar trace.get_current_span().set_attribute para usar fake_set
    # assert captured["user.id"] == "user-abc"
    # assert captured["auth.channel"] == "tg"
```

- [ ] **Step 4: Run all tests + lint**

```bash
uv run pytest --cov=. --cov-report=term-missing
uv run ruff check .
```

- [ ] **Step 5: Commit**

```bash
git add wasp/telemetry.py wasp/provision.py tests/test_telemetry.py tests/test_provision.py
git commit -m "feat(telemetry): add wasp_auth_denied_total + user.id span attribute"
```

---

### Task 7: Configuração e runbook

**Files:**
- Modify: `.env.example`
- Create: `docs/runbooks/auth-admin.md`
- Modify: `docs/runbooks/validation.md`

- [ ] **Step 1: Update `.env.example`**

```bash

# Auth (multi-channel allowlist)
# WASP_AGENT_DB_FILE=agent.db
# WASP_AGENT_INVITE_TTL_HOURS=1
# TELEGRAM_BOT_USERNAME=your_bot_name   # required for admin-invite link generation
```

- [ ] **Step 2: Write `docs/runbooks/auth-admin.md`**

Cobrir:

- **Bootstrap inicial** (uma vez por deploy): como descobrir seu próprio Telegram `user.id` (instrução: mandar mensagem ao bot `@userinfobot` ou similar); rodar `make admin-bootstrap NAME="Silvio" CHANNEL=tg ID=12345678`.
- **Convidar novo usuário**: `make admin-invite NAME="Alice"` → link `https://t.me/<Bot>?start=<token>` → enviar ao usuário por canal seguro.
- **Limitações conhecidas**: TTL 1h; revogação não interrompe tools em execução; não há multi-tenancy real (todo user pode provisionar qualquer tenant).
- **Revogar**: `make admin-revoke CHANNEL=tg ID=12345678`.
- **Listar**: `make admin-list`.
- **Como descobrir o `chat_id` de alguém** quando o link `/start` não funcionou: ver logs do `make run` filtrando por `auth denied`.
- **Canal `local` (local-chat / E2E):** NÃO passa por allowlist — é tratado como "operador confiável no host". O boundary de segurança é a rede: o endpoint AgentOS (`/agents/.../runs`) deve ouvir só `127.0.0.1` em produção. Se precisar de `local-chat` por rede, ver spec futuro `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` (CLI device flow / OAuth).

- [ ] **Step 3: Update `validation.md`**

No path B (smoke Telegram), adicionar pré-requisito: rodar `make admin-bootstrap ...` antes (ou desabilitar auth via env var? **não** — testar com auth ligado).

- [ ] **Step 4: Commit**

```bash
git add .env.example docs/runbooks/auth-admin.md docs/runbooks/validation.md
git commit -m "docs(runbooks): document auth admin workflow"
```

---

### Task 8: Inicialização automática do schema no startup

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

`auth.init_db()` precisa rodar no startup para garantir as tabelas, antes de qualquer request.

- [ ] **Step 1: Write failing test**

```python
def test_main_initializes_auth_db(mock_agno, monkeypatch):
    init_called = []
    monkeypatch.setattr("wasp.auth.init_db", lambda db_file=None: init_called.append(db_file))
    import main  # noqa: F401
    assert init_called  # init_db was called at import time
```

- [ ] **Step 2: Implement**

Em `main.py`, após o `os.umask(0o077)`:

```python
from wasp import auth  # noqa: E402
auth.init_db()
```

- [ ] **Step 3: Run all tests + lint**

```bash
uv run pytest --cov=. --cov-report=term-missing
uv run ruff check .
```

- [ ] **Step 4: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat(main): initialize auth schema at startup"
```

---

### Task 9: HANDOFF + spec status

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md`

- [ ] **Step 1: Mark spec as Implemented**

```
**Status:** Approved
```

para:

```
**Status:** Implemented
```

- [ ] **Step 2: Update `HANDOFF.md`**

- Remover a entrada "chat-id allowlist (prioridade alta)" de `## Next Steps`.
- Adicionar parágrafo em `## Current Progress` (Ciclo 7).
- Atualizar a tabela `Specs ativos`: spec auth → Implemented (arquivar depois do merge).
- Atualizar `Open Security Issues` se §9 do CLAUDE.md mudar de status.

- [ ] **Step 3: Verify tests still pass + lint clean**

```bash
uv run pytest --cov=. --cov-report=term-missing
uv run ruff check .
```

Expected: PASS, cobertura 100%, lint clean.

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md
git commit -m "docs: mark auth-multichannel spec Implemented and update HANDOFF"
```

Archive (mover para `archived/` por CLAUDE.md §7) acontece **após** merge em `main`, fora deste plano.

---

## Self-Review

- **Spec coverage:** todas as seções do spec (§4 schema, §5.1 módulo, §5.2 guard, §5.3 CLI, §6 config, §7 spans, §8 métrica, §11.1 bootstrap, §11.2 mensagens) mapeadas em tasks.
- **Verificação:** unit tests cobrem `auth.py` integralmente; testes do guard em `provision.py`; teste de `/start <token>` em `test_main.py`; teste da métrica.
- **Out of scope respeitado:** sem OAuth, sem CLI device flow, sem multi-tenancy, sem rate limiting, sem 2FA.
- **Risco aberto:** Task 3 depende de investigação do agno Telegram interface. Se a integração não permitir registrar handler limpo para `/start`, o plano vai precisar de revisão (fallback: rota webhook custom antes do agno) — documentar no commit message.

---

## Done

Ao final, o operador consegue:

```bash
make admin-bootstrap NAME="Silvio" CHANNEL=tg ID=12345678   # primeira vez
make admin-invite NAME="Alice"                              # convida
# → repassa o link t.me/<Bot>?start=<token> para Alice
# Alice clica → bot responde "Bem-vindo, Alice"
# Alice usa o bot normalmente
make admin-list
make admin-revoke CHANNEL=tg ID=87654321
```

E qualquer `chat_id` desconhecido recebe silêncio total.
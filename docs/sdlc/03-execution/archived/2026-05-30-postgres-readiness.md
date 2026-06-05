# Postgres Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** preparar o código para a chegada do PostgreSQL — sem implementar o backend — abstraindo o `db=` do agno num novo módulo `wasp/sessions.py`, adicionando branch `elif backend == "postgres"` em `get_repository()` e `build_session_db()` com import condicional, e renomeando env vars `WASP_AGENT_DB_*` → `DATABASE_*`.

**Architecture:** novo módulo `wasp/sessions.py::build_session_db()` simétrico a `wasp/models.py::build_model()`. Lê `DATABASE_BACKEND`/`DATABASE_FILE` e retorna `SqliteDb` no branch sqlite (default). Branch postgres com `try: from agno.db.postgres import PostgresDb except ImportError → NotImplementedError`. Mesma estrutura em `wasp/auth/__init__.py::get_repository()`. Renomeação coordenada das env vars em código, testes, docs e `.env*`.

**Tech Stack:** Python 3.x, agno (mockado em testes via `mock_agno`), pytest, ruff, radon, SQLite via `sqlite3` stdlib.

**Spec:** `docs/sdlc/02-design/2026-05-30-postgres-readiness.md`

---

## Estrutura de arquivos

**Novos:**
- `wasp/sessions.py` — `build_session_db()` builder
- `tests/test_sessions.py` — cobertura do builder

**Modificados (código):**
- `wasp/agent.py` — usa `build_session_db()`; remove import de `SqliteDb`
- `wasp/auth/__init__.py` — adiciona branch `elif backend == "postgres"`; rename env var
- `wasp/auth/_connection.py` — rename env var

**Modificados (testes):**
- `tests/conftest.py` — adicionar `wasp.sessions` nas listas de `sys.modules.pop`
- `tests/test_auth_repository.py` — rename env vars; substituir teste de "unsupported backend" por dois
- `tests/test_auth_cli.py` — rename env var na fixture
- `tests/test_agent.py` — sem mudança esperada (confirmar)

**Modificados (config/docs):**
- `.env` — adiciona bloco DATABASE_* (comentado)
- `.env.example` — adiciona bloco DATABASE_* (comentado); renomeia DB_FILE
- `CLAUDE.md` — nota sobre exceção `DATABASE_*` referenciando este spec
- `docs/runbooks/auth-admin.md` — rename env vars
- `docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md` — atualizar tabela
- `docs/sdlc/02-design/2026-05-30-postgres-readiness.md` — marcar como `Implemented` no fim

---

### Task 1: Rename env vars em `wasp/auth/_connection.py` e `wasp/auth/__init__.py`

Começamos pelo rename porque ele toca apenas leitura de env var — sem mudança de comportamento. Os testes existentes precisarão ser atualizados juntos.

**Files:**
- Modify: `wasp/auth/_connection.py:6-9`
- Modify: `wasp/auth/__init__.py:14`
- Modify: `tests/test_auth_repository.py:194,230,266,277`
- Modify: `tests/test_auth_cli.py:8`

- [ ] **Step 1: Rodar testes baseline (devem passar)**

```bash
cd /home/silvios/git/wasp-agent
uv run pytest tests/test_auth_repository.py tests/test_auth_cli.py -v
```

Expected: PASS.

- [ ] **Step 2: Renomear env var em `wasp/auth/_connection.py`**

```python
# wasp/auth/_connection.py
import os
import sqlite3
from datetime import datetime, timezone


def _resolve_db_file(db_file: str | None) -> str:
    if db_file is not None:
        return db_file
    return os.getenv("DATABASE_FILE", "agent.db")


def _connect(db_file: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_file)
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 3: Renomear env var em `wasp/auth/__init__.py`**

```python
import os

from wasp.auth.protocol import AuthRepository as AuthRepository
from wasp.auth.sqlite_repository import SqliteAuthRepository as SqliteAuthRepository

__all__ = ["AuthRepository", "SqliteAuthRepository", "get_repository"]

_repository: AuthRepository | None = None


def get_repository() -> AuthRepository:
    global _repository
    if _repository is None:
        backend = os.getenv("DATABASE_BACKEND", "sqlite")
        if backend == "sqlite":
            _repository = SqliteAuthRepository()
        else:
            raise ValueError(f"unsupported backend: {backend}")
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None
```

- [ ] **Step 4: Atualizar testes — `tests/test_auth_repository.py`**

Substituir 4 ocorrências:

- Linha 194: `monkeypatch.setenv("WASP_AGENT_DB_FILE", target)` → `monkeypatch.setenv("DATABASE_FILE", target)`
- Linha 230: idem
- Linha 266: `monkeypatch.setenv("WASP_AGENT_DB_FILE", str(tmp_path / "singleton.db"))` → `monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "singleton.db"))`
- Linha 277: `monkeypatch.setenv("WASP_AGENT_DB_BACKEND", "postgres")` → `monkeypatch.setenv("DATABASE_BACKEND", "mongo")` (motivo: vamos manter este teste como "backend inválido genérico"; o branch postgres ganha NotImplementedError na Task 4, e o teste correspondente é criado lá)

Renomear também o nome da função na linha 276 para refletir o backend inválido genérico:

```python
def test_get_repository_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "mongo")
    from wasp import auth

    auth._reset_repository()
    with pytest.raises(ValueError, match="unsupported backend"):
        auth.get_repository()
    auth._reset_repository()
```

- [ ] **Step 5: Atualizar fixture em `tests/test_auth_cli.py`**

Linha 8: `monkeypatch.setenv("WASP_AGENT_DB_FILE", str(tmp_path / "agent.db"))` → `monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "agent.db"))`

- [ ] **Step 6: Rodar testes e confirmar verde**

```bash
uv run pytest tests/test_auth_repository.py tests/test_auth_cli.py -v
```

Expected: PASS (mesmos testes de antes, agora com env vars novas).

- [ ] **Step 7: Rodar suite completa**

```bash
make test
```

Expected: PASS, coverage 100%.

- [ ] **Step 8: Commit**

```bash
git add wasp/auth/_connection.py wasp/auth/__init__.py tests/test_auth_repository.py tests/test_auth_cli.py
git commit -m "refactor(auth): rename WASP_AGENT_DB_{BACKEND,FILE} -> DATABASE_{BACKEND,FILE}

Drop the WASP_AGENT_ prefix for database env vars to align with the universal
DATABASE_URL convention. The first formal exception to the WASP_AGENT_* rule
documented in CLAUDE.md; broader prefix decision tracked in
docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md.

Spec: docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
```

---

### Task 2: Criar `wasp/sessions.py` com branch sqlite

Builder simétrico a `wasp/models.py::build_model()`. Começamos com apenas o branch sqlite (e o `else: raise ValueError`) para fechar verde rapidamente — o branch postgres entra na Task 5.

**Files:**
- Create: `wasp/sessions.py`
- Create: `tests/test_sessions.py`
- Modify: `tests/conftest.py` (adicionar `wasp.sessions` nas duas listas de `sys.modules.pop`)

- [ ] **Step 1: Escrever testes que falham**

Criar `tests/test_sessions.py`:

```python
import pytest


def test_build_session_db_defaults_to_sqlite(mock_agno, monkeypatch):
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_FILE", raising=False)

    from wasp.sessions import build_session_db

    build_session_db()

    mock_agno["agno.db.sqlite.sqlite"].SqliteDb.assert_called_once_with(
        db_file="agent.db", session_table="agent_sessions"
    )


def test_build_session_db_sqlite_reads_database_file(mock_agno, monkeypatch):
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    monkeypatch.setenv("DATABASE_FILE", "/tmp/custom.db")

    from wasp.sessions import build_session_db

    build_session_db()

    mock_agno["agno.db.sqlite.sqlite"].SqliteDb.assert_called_once_with(
        db_file="/tmp/custom.db", session_table="agent_sessions"
    )


def test_build_session_db_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "mongo")

    from wasp.sessions import build_session_db

    with pytest.raises(ValueError, match="unsupported backend: mongo"):
        build_session_db()
```

- [ ] **Step 2: Adicionar `wasp.sessions` a `tests/conftest.py`**

Adicionar a linha `"wasp.sessions",` em **ambas** as listas `sys.modules.pop` (setup ~linha 60 e teardown ~linha 150). Posicionar imediatamente após `"wasp.agent",`:

```python
        "wasp.agent",
        "wasp.sessions",
        "wasp.clients",
```

(Aplicar nos dois loops — sem isso state vaza entre testes, ver `tests/CLAUDE.md`.)

- [ ] **Step 3: Rodar testes — devem falhar (módulo não existe)**

```bash
uv run pytest tests/test_sessions.py -v
```

Expected: FAIL com `ModuleNotFoundError: No module named 'wasp.sessions'`.

- [ ] **Step 4: Criar `wasp/sessions.py` com branch sqlite**

```python
import os


def build_session_db():
    backend = os.getenv("DATABASE_BACKEND", "sqlite")
    if backend == "sqlite":
        from agno.db.sqlite.sqlite import SqliteDb

        return SqliteDb(
            db_file=os.getenv("DATABASE_FILE", "agent.db"),
            session_table="agent_sessions",
        )
    raise ValueError(f"unsupported backend: {backend}")
```

- [ ] **Step 5: Rodar testes — devem passar**

```bash
uv run pytest tests/test_sessions.py -v
```

Expected: PASS (3 testes).

- [ ] **Step 6: Rodar suite completa**

```bash
make test
```

Expected: PASS, coverage 100% (a Task 5 cobrirá o branch postgres).

- [ ] **Step 7: Commit**

```bash
git add wasp/sessions.py tests/test_sessions.py tests/conftest.py
git commit -m "feat(sessions): add build_session_db() with sqlite branch

Mirrors wasp.models.build_model(). Reads DATABASE_BACKEND/DATABASE_FILE.
SQLite-only for now; the postgres branch comes next.

Spec: docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
```

---

### Task 3: `wasp/agent.py` passa a usar `build_session_db()`

**Files:**
- Modify: `wasp/agent.py:2,36` (remove import de `SqliteDb`; substitui literal por chamada do builder)
- Modify: `tests/test_agent.py` (provavelmente sem mudança — confirmar)

- [ ] **Step 1: Rodar test_agent.py baseline**

```bash
uv run pytest tests/test_agent.py -v
```

Expected: PASS.

- [ ] **Step 2: Editar `wasp/agent.py`**

Trocar o import e a linha do `db=`:

```python
from agno.agent import Agent

from wasp import list_platform_instances, provision_platform_instance
from wasp.models import build_model
from wasp.sessions import build_session_db

INSTRUCTIONS = [
    # ... inalterado ...
]


def build_agent() -> Agent:
    return Agent(
        name="wasp-agent",
        model=build_model(),
        db=build_session_db(),
        add_history_to_context=True,
        instructions=INSTRUCTIONS,
        tools=[provision_platform_instance, list_platform_instances],
    )
```

(Linha 2 `from agno.db.sqlite.sqlite import SqliteDb` é removida; linha 36 `db=SqliteDb(...)` vira `db=build_session_db()`.)

- [ ] **Step 3: Rodar test_agent.py**

```bash
uv run pytest tests/test_agent.py -v
```

Expected: PASS. O assert em `tests/test_agent.py:13-15` (`mock_agno["agno.db.sqlite.sqlite"].SqliteDb.assert_called_once_with(db_file="agent.db", session_table="agent_sessions")`) deve continuar válido — `build_session_db()` chama o mesmo `SqliteDb` com os mesmos args.

Se falhar com algo do tipo "SqliteDb called twice": pode ser que `mock_agno` já tenha capturado uma chamada prévia. Inspecionar `mock_agno["agno.db.sqlite.sqlite"].SqliteDb.call_args_list` — se for o caso, é estado vazado e indica falha do `sys.modules.pop` (revisar Task 2 Step 2).

- [ ] **Step 4: Rodar suite completa**

```bash
make test
```

Expected: PASS, coverage 100%.

- [ ] **Step 5: Commit**

```bash
git add wasp/agent.py
git commit -m "refactor(agent): use build_session_db() instead of inline SqliteDb

Removes the hardcoded db_file=\"agent.db\" path and the top-level SqliteDb
import. build_agent() now delegates session backend selection to
wasp.sessions.build_session_db().

Spec: docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
```

---

### Task 4: Adicionar branch postgres em `wasp/auth/__init__.py::get_repository()`

Import condicional com `NotImplementedError`. Adicionar teste do novo branch.

**Files:**
- Modify: `wasp/auth/__init__.py`
- Modify: `tests/test_auth_repository.py` (adicionar teste do branch postgres)

- [ ] **Step 1: Escrever o teste novo (falha esperada)**

Adicionar ao final de `tests/test_auth_repository.py`:

```python
def test_get_repository_postgres_raises_not_implemented(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "postgres")
    from wasp import auth

    auth._reset_repository()
    with pytest.raises(NotImplementedError, match="Postgres backend not yet implemented"):
        auth.get_repository()
    auth._reset_repository()
```

- [ ] **Step 2: Rodar o teste novo — deve falhar**

```bash
uv run pytest tests/test_auth_repository.py::test_get_repository_postgres_raises_not_implemented -v
```

Expected: FAIL — atualmente `DATABASE_BACKEND=postgres` levanta `ValueError`, não `NotImplementedError`.

- [ ] **Step 3: Adicionar branch postgres em `wasp/auth/__init__.py`**

```python
import os

from wasp.auth.protocol import AuthRepository as AuthRepository
from wasp.auth.sqlite_repository import SqliteAuthRepository as SqliteAuthRepository

__all__ = ["AuthRepository", "SqliteAuthRepository", "get_repository"]

_repository: AuthRepository | None = None


def get_repository() -> AuthRepository:
    global _repository
    if _repository is None:
        backend = os.getenv("DATABASE_BACKEND", "sqlite")
        if backend == "sqlite":
            _repository = SqliteAuthRepository()
        elif backend == "postgres":
            try:
                from wasp.auth.postgres_repository import PostgresAuthRepository
            except ImportError as e:
                raise NotImplementedError(
                    "Postgres backend not yet implemented "
                    "(wasp/auth/postgres_repository.py missing). "
                    "See docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
                ) from e
            _repository = PostgresAuthRepository()
        else:
            raise ValueError(f"unsupported backend: {backend}")
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None
```

(O módulo `wasp/auth/postgres_repository.py` **não** existe — esse é o ponto. O `ImportError` real dispara o `NotImplementedError`.)

- [ ] **Step 4: Rodar o teste novo — deve passar**

```bash
uv run pytest tests/test_auth_repository.py::test_get_repository_postgres_raises_not_implemented -v
```

Expected: PASS.

- [ ] **Step 5: Rodar suite completa**

```bash
make test
```

Expected: PASS, coverage 100%. Branches cobertos: sqlite (default — vários testes), postgres+ImportError (teste novo), unknown backend (`test_get_repository_unknown_backend_raises_value_error` da Task 1).

Se algum branch ficar descoberto: pode ser que o `try`/`except ImportError` exija também um teste onde o import **funciona**. Como `wasp.auth.postgres_repository` nunca existe neste spec, esse branch (linha `_repository = PostgresAuthRepository()`) fica como código morto até a implementação futura — `# pragma: no cover` nessa linha **única** é aceitável e justificado (cargo sem teste). Adicionar somente se `make test` cobrir < 100%.

- [ ] **Step 6: Commit**

```bash
git add wasp/auth/__init__.py tests/test_auth_repository.py
git commit -m "feat(auth): add postgres branch in get_repository() with NotImplementedError

Conditional import of wasp.auth.postgres_repository — module doesn't exist
yet, so ImportError fires and the user gets a clear NotImplementedError
pointing at the readiness spec. The slot is now visible in the code.

Spec: docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
```

---

### Task 5: Adicionar branch postgres em `wasp/sessions.py::build_session_db()`

Mesmo padrão da Task 4: import condicional de `agno.db.postgres` que dispara `NotImplementedError`.

**Files:**
- Modify: `wasp/sessions.py`
- Modify: `tests/test_sessions.py`
- Possibly modify: `tests/conftest.py` (se `agno.db.postgres` precisar **não** estar no `AGNO_MODULES`)

- [ ] **Step 1: Confirmar que `agno.db.postgres` NÃO está mockado**

```bash
grep -n "agno.db.postgres" /home/silvios/git/wasp-agent/tests/conftest.py
```

Expected: nenhum resultado. Se aparecer: remover da lista `AGNO_MODULES` (não queremos que esteja mockado — precisamos que o `ImportError` real dispare).

- [ ] **Step 2: Escrever o teste do branch postgres (falha esperada)**

Adicionar ao `tests/test_sessions.py`:

```python
def test_build_session_db_postgres_raises_not_implemented(mock_agno, monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "postgres")

    from wasp.sessions import build_session_db

    with pytest.raises(NotImplementedError, match="Postgres backend for agno sessions not yet wired"):
        build_session_db()
```

- [ ] **Step 3: Rodar o teste — deve falhar**

```bash
uv run pytest tests/test_sessions.py::test_build_session_db_postgres_raises_not_implemented -v
```

Expected: FAIL com `ValueError: unsupported backend: postgres` (ainda não temos o branch).

- [ ] **Step 4: Adicionar branch postgres em `wasp/sessions.py`**

```python
import os


def build_session_db():
    backend = os.getenv("DATABASE_BACKEND", "sqlite")
    if backend == "sqlite":
        from agno.db.sqlite.sqlite import SqliteDb

        return SqliteDb(
            db_file=os.getenv("DATABASE_FILE", "agent.db"),
            session_table="agent_sessions",
        )
    elif backend == "postgres":
        try:
            from agno.db.postgres import PostgresDb
        except ImportError as e:
            raise NotImplementedError(
                "Postgres backend for agno sessions not yet wired. "
                "See docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
            ) from e
        return PostgresDb(db_url=os.environ["DATABASE_URL"])
    raise ValueError(f"unsupported backend: {backend}")
```

- [ ] **Step 5: Rodar o teste — deve passar**

```bash
uv run pytest tests/test_sessions.py::test_build_session_db_postgres_raises_not_implemented -v
```

Expected: PASS.

Se falhar com algo como "AttributeError on PostgresDb" em vez de `NotImplementedError`: significa que `agno.db.postgres` está sendo mockado por engano. Voltar ao Step 1 e remover dos mocks.

- [ ] **Step 6: Rodar suite completa**

```bash
make test
```

Expected: PASS, coverage 100%. A linha `return PostgresDb(db_url=...)` continua não-coberta (módulo `agno.db.postgres` não existe). Aceitável `# pragma: no cover` na linha única se necessário; tentar sem primeiro.

- [ ] **Step 7: Commit**

```bash
git add wasp/sessions.py tests/test_sessions.py
git commit -m "feat(sessions): add postgres branch in build_session_db() with NotImplementedError

Conditional import of agno.db.postgres — when (eventually) installed,
this branch instantiates PostgresDb(db_url=DATABASE_URL). For now, the
ImportError raises NotImplementedError pointing at the spec.

Spec: docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
```

---

### Task 6: Atualizar `.env`, `.env.example`, `CLAUDE.md`, `docs/runbooks/auth-admin.md`

Sem código novo — apenas docs e config para refletir os novos nomes e a exceção formalizada.

**Files:**
- Modify: `.env`
- Modify: `.env.example`
- Modify: `CLAUDE.md:111`
- Modify: `docs/runbooks/auth-admin.md:115-116,126`
- Modify: `docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`
- Modify: `docs/sdlc/02-design/2026-05-30-postgres-readiness.md` (marcar Status: Implemented)

- [ ] **Step 1: Atualizar `.env.example`**

Substituir a linha `# WASP_AGENT_DB_FILE=agent.db` (linha 46) e o bloco ao redor por:

```bash
# Auth (multi-channel allowlist) — ver docs/runbooks/auth-admin.md

# Backend de persistência (auth + sessões agno).
# Valores: 'sqlite' (default), 'postgres' (ainda não implementado — ver
# docs/sdlc/02-design/2026-05-30-postgres-readiness.md).
# DATABASE_BACKEND=sqlite

# Path do arquivo SQLite — ignorado se DATABASE_BACKEND != sqlite.
# DATABASE_FILE=agent.db

# DSN do Postgres — ignorado se DATABASE_BACKEND=sqlite.
# Exemplo: postgresql://user:pass@localhost:5432/wasp_agent
# DATABASE_URL=

# WASP_AGENT_INVITE_TTL_HOURS=1
```

- [ ] **Step 2: Atualizar `.env`**

Mesmo bloco do Step 1, também comentado (não setar nada — defaults bastam para dev local). Adicionar logo após o bloco de auth (ou onde a linha antiga `WASP_AGENT_DB_FILE` estava, se existir).

- [ ] **Step 3: Atualizar `CLAUDE.md`**

Substituir linha 111:

```markdown
### Env vars

Agent configuration uses prefix `WASP_AGENT_` (e.g., `WASP_AGENT_NOTIFIER`).

Exceção: variáveis de database usam o prefixo universal `DATABASE_*`
(`DATABASE_BACKEND`, `DATABASE_FILE`, `DATABASE_URL`) — alinhado com a
convenção de `DATABASE_URL`. Ver
`docs/sdlc/02-design/2026-05-30-postgres-readiness.md` e
`docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`.
```

- [ ] **Step 4: Atualizar `docs/runbooks/auth-admin.md`**

Substituir nas linhas 115-116:

```markdown
| `DATABASE_BACKEND` | `sqlite` | `sqlite` \| `postgres` | `sqlite` usa `SqliteAuthRepository` apontando para `DATABASE_FILE` (default `agent.db`). `postgres` ainda não implementado — levanta `NotImplementedError`. Outros valores levantam `ValueError`. |
| `DATABASE_FILE` | `agent.db` | path | Arquivo SQLite. Ignorado se `DATABASE_BACKEND` não for `sqlite`. |
```

Linha 126: `agent.db` permanece (é o nome real do arquivo em disco — não é env var).

- [ ] **Step 5: Atualizar `docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`**

Atualizar a tabela "Estado atual" (seção 1) — remover `WASP_AGENT_DB_BACKEND` e `WASP_AGENT_DB_FILE` (não usam mais o prefixo). Resultado:

```markdown
| Variável | Onde |
|---|---|
| `WASP_AGENT_NOTIFIER` | `wasp/clients/__init__.py` (override de canal) |
| `WASP_AGENT_INVITE_TTL_HOURS` | `wasp/auth/sqlite_repository.py` |
```

Adicionar nota no fim da seção 1: "Variáveis de database (`DATABASE_BACKEND`, `DATABASE_FILE`, `DATABASE_URL`) saíram do prefixo `WASP_AGENT_*` em 2026-05-30 — ver `docs/sdlc/02-design/2026-05-30-postgres-readiness.md`."

Remover também a linha em "Próximas vars que entrariam: `WASP_AGENT_DB_URL` ..." (seção 3) — já foi para `DATABASE_URL`.

- [ ] **Step 6: Marcar spec como `Implemented`**

Em `docs/sdlc/02-design/2026-05-30-postgres-readiness.md`, linha 3:

```markdown
**Status:** Implemented
```

- [ ] **Step 7: Rodar validação completa**

```bash
make format
make test
make cc
```

Expected: PASS em todos. `make cc` deve mostrar complexidade ≤ B em `wasp/sessions.py` e `wasp/auth/__init__.py`.

- [ ] **Step 8: Rodar e2e**

```bash
make e2e-with-debug
```

Expected: PASS. Exercita `build_agent()` → `build_session_db()` → `SqliteDb(db_file="agent.db", session_table="agent_sessions")` com defaults.

- [ ] **Step 9: Verificação manual smoke**

```bash
unset DATABASE_BACKEND DATABASE_FILE DATABASE_URL

# sessions: sqlite default
uv run python -c "from wasp.sessions import build_session_db; print(build_session_db())"
# Esperado: instância de SqliteDb (ou repr da classe agno)

# sessions: postgres falha rápido
DATABASE_BACKEND=postgres uv run python -c "from wasp.sessions import build_session_db; build_session_db()"
# Esperado: NotImplementedError: Postgres backend for agno sessions not yet wired. ...

# sessions: backend desconhecido
DATABASE_BACKEND=mongo uv run python -c "from wasp.sessions import build_session_db; build_session_db()"
# Esperado: ValueError: unsupported backend: mongo

# auth: postgres falha rápido
DATABASE_BACKEND=postgres uv run python -c "from wasp.auth import get_repository; get_repository()"
# Esperado: NotImplementedError: Postgres backend not yet implemented ...
```

- [ ] **Step 10: Commit final**

```bash
git add .env .env.example CLAUDE.md docs/runbooks/auth-admin.md \
        docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md \
        docs/sdlc/02-design/2026-05-30-postgres-readiness.md
git commit -m "docs(postgres-readiness): update .env*, CLAUDE.md, runbook; mark spec Implemented

- .env / .env.example: document DATABASE_BACKEND, DATABASE_FILE, DATABASE_URL (all commented)
- CLAUDE.md: formalize DATABASE_* as the documented exception to WASP_AGENT_* prefix
- runbook auth-admin.md: rename env vars, note postgres branch raises NotImplementedError
- env-var-prefix-naming exploration: reflect that DATABASE_* already left the prefix
- mark postgres-readiness spec as Implemented

Spec: docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §3 convenção env vars | Task 1 (auth), Task 2 (sessions), Task 6 (docs/.env) |
| §4 wasp/sessions.py | Task 2 (sqlite), Task 5 (postgres branch) |
| §5 branch postgres auth | Task 4 |
| §6 .env.example/.env | Task 6 |
| §7 rename coordenado | Task 1 (code + tests auth), Task 6 (docs/.env/CLAUDE.md) |
| §8 testes novos | Task 2 (sessions sqlite), Task 4 (auth postgres), Task 5 (sessions postgres) |
| §9 validação (make format/test/cc/e2e) | Task 6 Steps 7-9 |
| §10 arquivos alterados | mapeado nas Files de cada task |
| §11 risco mock_agno postgres | Task 5 Step 1 (guard explícito) |
| §12 specs próximos | fora deste plano (acionável depois) |

Tudo coberto.

**2. Placeholder scan:** sem TBD/TODO/"implementar depois". Cada step tem código real ou comando real.

**3. Type consistency:**

- `build_session_db()` — assinatura idêntica nas Tasks 2 e 5.
- `get_repository()` — assinatura preservada; só ganha um branch.
- `DATABASE_BACKEND` / `DATABASE_FILE` / `DATABASE_URL` — escritos identicamente em todo o plano.
- `NotImplementedError` — mesma classe nas duas Tasks (4 e 5), mensagens distintas mas referenciando o mesmo spec.

Consistente.

---

## Execution Handoff

**Plan complete and saved to `docs/sdlc/03-execution/2026-05-30-postgres-readiness.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — eu despacho um subagent fresh por task, com review entre tasks, iteração rápida.

**2. Inline Execution** — executa tasks nesta sessão usando executing-plans, batch execution com checkpoints.

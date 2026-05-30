# Preparação para PostgreSQL — abstração sem implementação

**Status:** Implemented
**Data:** 2026-05-30
**Motivação:** preparar o código para a chegada do PostgreSQL sem migrar dados nem implementar o backend. Remover hardcodes (path do SQLite em `wasp/agent.py`), simetrizar a abstração de sessões agno com a abstração já existente de auth, e deixar os branches `elif backend == "postgres"` explícitos no código, com import condicional, para servirem de "slot" visível ao backend futuro.

**Pós-implementação:** `agno.db.postgres` está presente no agno upstream — o branch postgres em `wasp/sessions.py` está, de fato, **funcional** quando `DATABASE_URL` é fornecido. Apenas o branch postgres em `wasp/auth/__init__.py` permanece como slot (`NotImplementedError`), aguardando o `PostgresAuthRepository` (próximo spec).

---

## 1. Contexto

Estado atual:

- **Auth** (`wasp/auth/`) já está praticamente preparado. `AuthRepository` Protocol existe (`protocol.py`), factory `get_repository()` em `__init__.py` tem `if backend == "sqlite": ... else: raise ValueError`. Falta o branch `elif backend == "postgres"`.
- **Sessões agno** (`wasp/agent.py:36`): `db=SqliteDb(db_file="agent.db", session_table="agent_sessions")` com path **hardcoded** e classe `SqliteDb` importada no topo do módulo. Zero abstração — troca de backend é literal swap.
- Env vars hoje: `WASP_AGENT_DB_BACKEND`, `WASP_AGENT_DB_FILE`. O auth lê ambas; o `agent.py` não lê nenhuma.

Designs prévios já anteciparam Postgres como próximo passo:

- `docs/sdlc/02-design/2026-05-30-auth-repository.md` (`Status: Implemented`).
- `docs/sdlc/02-design/2026-05-30-auth-singleton-migration.md` (`Status: Implemented`).

Este spec consolida a preparação restante.

---

## 2. Escopo

**In-scope:**

- Novo módulo `wasp/sessions.py::build_session_db()` simétrico a `wasp/models.py::build_model()`.
- Branch `elif backend == "postgres"` com import condicional em `wasp/auth/__init__.py::get_repository()` e em `wasp/sessions.py::build_session_db()`.
- Renomear env vars `WASP_AGENT_DB_BACKEND` → `DATABASE_BACKEND`, `WASP_AGENT_DB_FILE` → `DATABASE_FILE`. Adicionar `DATABASE_URL` como nome canônico do DSN futuro.
- Atualizar testes, `.env.example`, `.env`, `CLAUDE.md`, `docs/runbooks/auth-admin.md`, `docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`.

**Out-of-scope (specs próprios):**

- Implementação do `PostgresAuthRepository`.
- Troca real do `SqliteDb` por `PostgresDb` no agno.
- Mudanças no `Dockerfile` / `docker-compose` / volumes persistentes.
- Renomeação geral do prefixo `WASP_AGENT_*` para o restante das vars do projeto (`WASP_AGENT_NOTIFIER`, `WASP_AGENT_URL`, etc.) — ver `docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`.

---

## 3. Convenção final de env vars

| Variável | Função |
|---|---|
| `DATABASE_BACKEND` | `sqlite` (default) \| `postgres` (auth ainda não implementado; agno sessions funcional) |
| `DATABASE_FILE` | path do SQLite (default `agent.db`) — ignorado se backend != sqlite |
| `DATABASE_URL` | DSN do Postgres — ignorado se backend == sqlite |

`DATABASE_URL` é convenção universal (Heroku/Postgres/SQLAlchemy). Drop completo do prefixo `WASP_AGENT_` para vars de database é coerente com isso.

Implicação: este spec é a primeira exceção formal à regra do `CLAUDE.md` ("Agent configuration uses prefix `WASP_AGENT_`"). A regra é atualizada para citar a exceção e referenciar este spec.

---

## 4. Novo módulo `wasp/sessions.py`

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
        from agno.db.postgres import PostgresDb

        return PostgresDb(db_url=os.environ["DATABASE_URL"])
    raise ValueError(f"unsupported backend: {backend}")
```

Decisões:

- Lê a mesma `DATABASE_BACKEND` usada por `wasp.auth.get_repository()` — single source of truth.
- `DATABASE_FILE` continua servindo auth e sessions — um único arquivo SQLite para ambos no modo sqlite, mantendo o comportamento de hoje.
- Imports tardios (dentro de cada branch) — setar `DATABASE_BACKEND=postgres` não exige `agno.db.sqlite` instalado, e vice-versa.
- Retorno **sem type annotation** — para não importar tipos do agno no topo (agno reorganiza módulos com frequência). Match com `wasp/models.py::build_model()`.

`wasp/agent.py` passa a usar o builder:

```python
from agno.agent import Agent

from wasp import list_platform_instances, provision_platform_instance
from wasp.models import build_model
from wasp.sessions import build_session_db

...

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

O import de `SqliteDb` no topo de `wasp/agent.py` desaparece.

---

## 5. Branch postgres em `wasp/auth/__init__.py::get_repository()`

```python
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
```

Decisões:

- Import condicional **dentro** do branch — mesmo padrão do `build_session_db()`. `grep -rn "postgres" wasp/auth/` acha o slot sem cavar a árvore.
- `NotImplementedError` (e não `ValueError`) sinaliza "isso vai existir, só não foi implementado". `ValueError` continua para backends que não estão planejados (`mysql`, `mongo`).
- Lazy import: quem fica em SQLite nunca carrega `psycopg`/`asyncpg`.
- O construtor futuro `PostgresAuthRepository()` lerá `DATABASE_URL` internamente (simétrico a `SqliteAuthRepository()` lendo `DATABASE_FILE`). Esse contrato será congelado no spec de implementação do Postgres.

---

## 6. Mudanças em `.env.example` e `.env`

**`.env.example`** — substituir a linha 46 e adicionar bloco logo após `WASP_AGENT_INVITE_TTL_HOURS=1`:

```bash
# Backend de persistência (auth + sessões agno).
# Valores: 'sqlite' (default), 'postgres' (ainda não implementado — ver
# docs/sdlc/02-design/2026-05-30-postgres-readiness.md).
# DATABASE_BACKEND=sqlite

# Path do arquivo SQLite — ignorado se DATABASE_BACKEND != sqlite.
# DATABASE_FILE=agent.db

# DSN do Postgres — ignorado se DATABASE_BACKEND=sqlite.
# Exemplo: postgresql://user:pass@localhost:5432/wasp_agent
# DATABASE_URL=
```

**`.env`** — espelhar o mesmo bloco (também comentado). Default `sqlite` + `agent.db` continua funcionando sem qualquer linha descomentada.

Justificativa de manter tudo comentado:
- Defaults já estão no código.
- `DATABASE_URL` vazio com `DATABASE_BACKEND=postgres` falharia no `os.environ["DATABASE_URL"]` — comentado é mais seguro.

---

## 7. Renomeação coordenada de env vars

Substituição global `WASP_AGENT_DB_BACKEND` → `DATABASE_BACKEND` e `WASP_AGENT_DB_FILE` → `DATABASE_FILE`.

Código:

- `wasp/auth/_connection.py:9`
- `wasp/auth/__init__.py:14`
- `wasp/sessions.py` (novo)

Testes:

- `tests/test_auth_repository.py` (4 ocorrências: `:192-201`, `:228-229`, `:276-281`, mais nomes de teste opcionais)
- `tests/test_auth_cli.py:7-8`

Docs e config:

- `CLAUDE.md` — seção "Env vars" passa a citar a exceção `DATABASE_*` e referenciar este spec.
- `docs/runbooks/auth-admin.md:115-116`
- `.env.example`, `.env`
- `docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md` — atualizar a tabela (remover `WASP_AGENT_DB_BACKEND` e `WASP_AGENT_DB_FILE`; marcar `DATABASE_*` como já fora do prefixo).

**Specs históricos** (`2026-05-30-auth-repository.md`, `2026-05-30-auth-singleton-migration.md`): `Status: Implemented`. Não reescrever — basta este spec mencionar que os nomes foram atualizados depois.

**Sem aliasing.** Quem tiver `.env` local com `WASP_AGENT_DB_FILE=...` atualiza manualmente. Footprint pequeno (projeto novo) — aliasing seria código permanente para ganho marginal.

---

## 8. Testes

### Novo: `tests/test_sessions.py`

```python
def test_build_session_db_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    monkeypatch.setenv("DATABASE_FILE", "test.db")
    db = build_session_db()
    # asserts: SqliteDb chamado com db_file="test.db", session_table="agent_sessions"

def test_build_session_db_sqlite_uses_default_file(monkeypatch):
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_FILE", raising=False)
    # asserts: SqliteDb chamado com db_file="agent.db"

def test_build_session_db_postgres_raises_not_implemented(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "postgres")
    with pytest.raises(NotImplementedError, match="not yet wired"):
        build_session_db()

def test_build_session_db_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "mongo")
    with pytest.raises(ValueError, match="unsupported backend"):
        build_session_db()
```

O teste de postgres depende de `agno.db.postgres` **não** estar mockado em `mock_agno`. Verificar `tests/conftest.py` no plano — pode precisar ajuste.

### Alterado: `tests/test_auth_repository.py:276-281`

Substituir o teste único por dois:

```python
def test_get_repository_postgres_raises_not_implemented(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "postgres")
    _reset_repository()
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        get_repository()

def test_get_repository_unsupported_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "mongo")
    _reset_repository()
    with pytest.raises(ValueError, match="unsupported backend"):
        get_repository()
```

Para o teste de postgres dar erro real: `wasp.auth.postgres_repository` não existe como módulo (garantido — não criamos neste spec).

### Sem mudança esperada: `tests/test_agent.py`

`build_agent()` passa a chamar `build_session_db()`, que ainda chama `SqliteDb` com os mesmos args. Os asserts existentes (mock de `SqliteDb`) devem continuar válidos. Confirmar no plano.

### Cobertura

100% deve ser mantido. Branches críticos cobertos:

- `if backend == "sqlite":` (default — vários testes)
- `elif backend == "postgres":` + `except ImportError` (testes novos)
- `else: raise ValueError` (testes novos)

---

## 9. Validação

Antes de mergear:

```bash
make format
make test
make cc
make e2e-with-debug
```

- `make test` — 100% coverage. Sem regressão.
- `make cc` — radon, complexidade mínima B. Spec é pequeno; score não deve subir.
- `make e2e-with-debug` — exercita `build_agent()` real → `build_session_db()` real → `SqliteDb(db_file="agent.db", ...)` com os mesmos args de hoje (DATABASE_FILE não setado, default vale).

### Verificação manual rápida

```bash
# Backend default
unset DATABASE_BACKEND DATABASE_FILE DATABASE_URL
python -c "from wasp.sessions import build_session_db; print(build_session_db())"

# Backend postgres falha rápido (sessions)
DATABASE_BACKEND=postgres python -c "from wasp.sessions import build_session_db; build_session_db()"
# NotImplementedError

# Backend postgres falha rápido (auth)
DATABASE_BACKEND=postgres python -c "from wasp.auth import get_repository; get_repository()"
# NotImplementedError

# Backend desconhecido
DATABASE_BACKEND=mongo python -c "from wasp.sessions import build_session_db; build_session_db()"
# ValueError("unsupported backend: mongo")
```

---

## 10. Arquivos alterados (resumo)

| Arquivo | Mudança |
|---|---|
| `wasp/sessions.py` | novo |
| `wasp/agent.py` | usa `build_session_db()`; remove import de `SqliteDb` |
| `wasp/auth/__init__.py` | adiciona `elif backend == "postgres"`; rename env var |
| `wasp/auth/_connection.py` | rename env var |
| `tests/test_sessions.py` | novo |
| `tests/test_auth_repository.py` | rename env vars; substitui teste 276-281 por dois |
| `tests/test_auth_cli.py` | rename env var na fixture |
| `tests/test_agent.py` | confirmar (provavelmente sem mudança) |
| `tests/conftest.py` | confirmar (possível ajuste em `mock_agno`) |
| `.env` | adiciona bloco DATABASE_* (comentado) |
| `.env.example` | adiciona bloco DATABASE_* (comentado); renomeia DB_FILE |
| `CLAUDE.md` | nota sobre exceção `DATABASE_*` |
| `docs/runbooks/auth-admin.md` | rename env vars |
| `docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md` | atualiza tabela |

---

## 11. Riscos

- **`mock_agno` mocka `agno.db.postgres` por engano** — o teste de `NotImplementedError` em sessions só funciona se o `ImportError` real disparar. Mitigação: o plano confirma em `tests/conftest.py` que apenas `agno.db.sqlite.sqlite` está na lista de mocks.
- **`.env` local de desenvolvedor com nome antigo** — sem aliasing, vars setadas como `WASP_AGENT_DB_FILE` deixam de surtir efeito silenciosamente. Mitigação: documentar no PR e na seção de migração do runbook `auth-admin.md`.
- **`init_schema` é chamado em import-time?** — checar se algum `import wasp.*` no startup já dispara construção do repositório/sessions antes de `load_dotenv()` rodar. `wasp/agent.py::build_agent()` é chamado em runtime, não em import; auth singleton é lazy. Risco baixo, confirmar no plano.

---

## 12. Próximos specs (depois deste)

1. **Postgres auth repository** — implementar `wasp/auth/postgres_repository.py`, troca `NotImplementedError` por instanciação real, define contrato do construtor (`DATABASE_URL`), DDL Postgres (TIMESTAMPTZ, UUID), troca `BEGIN IMMEDIATE` por `SELECT FOR UPDATE` ou serializable tx.
2. **Postgres sessions** — implementar troca para `agno.db.postgres.PostgresDb` (provavelmente trivial se agno já tem `PostgresDb`).
3. **Dockerfile / docker-compose / persistência** — service Postgres opcional no compose, remover assunção de SQLite no Dockerfile, definir volumes.
4. **Renomeação geral do prefixo `WASP_AGENT_*`** — quando o nome novo for decidido (ver `2026-05-30-env-var-prefix-naming.md`).
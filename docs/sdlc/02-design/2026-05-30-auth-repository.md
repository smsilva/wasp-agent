# Reorganização de `wasp/auth.py` em pacote com Repository Protocol

**Status:** Draft  
**Data:** 2026-05-30  
**Motivação:** organização — `wasp/auth.py` cresceu para 310 linhas misturando 4 responsabilidades (infraestrutura de DB, identidades, convites, bootstrap). Migração futura para Postgres justifica encapsulamento via Repository, evitando reescrita posterior dos call sites.

---

## 1. Contexto

`wasp/auth.py` hoje contém:

| Responsabilidade | Funções | Linhas aprox. |
|---|---|---|
| Infraestrutura DB | `_resolve_db_file`, `_connect`, `_now`, `init_db`, `_initialized_dbs`, `_DDL` | 65 |
| Identidades/usuários | `create_user`, `link_identity`, `is_authorized`, `list_identities`, `revoke`, `has_any_user` | 100 |
| Convites | `create_invite`, `redeem_invite` | 90 |
| Bootstrap | `bootstrap_admin` | 25 |

Consumidores diretos da API pública:

- `wasp/auth_guard.py` — `is_authorized`
- `wasp/auth_cli.py` — `bootstrap_admin`, `link_identity`, `create_invite`, `revoke`, `list_identities`
- `wasp/clients/telegram/webhook.py` — `is_authorized`, `redeem_invite`, `has_any_user`
- `wasp/clients/discord/bot.py` — `is_authorized`, `redeem_invite`, `has_any_user`
- `main.py` — uso indireto
- `tests/test_auth.py`, `tests/test_auth_cli.py`, `tests/e2e/conftest.py`

A migração futura para Postgres é o caso de uso real que justifica abstração — sem isso, Repository seria cargo cult.

---

## 2. Decisões de design

**Único `AuthRepository`** cobrindo o bounded context inteiro (9 métodos). Splits artificiais (`UsersRepository` + `InvitesRepository`) deixariam órfãs as operações transacionais que cruzam tabelas (`redeem_invite`, `bootstrap_admin`).

**`Protocol` (PEP 544)**, não `ABC`. Structural typing é idiomático em Python moderno; não há necessidade de herança forçada nem implementação base compartilhada.

**Singleton via `get_repository()` + shims funcionais** no `__init__.py`. Preserva 100% dos call sites atuais (`auth.is_authorized(...)` continua funcionando). Migração para injeção explícita fica como opção futura.

**Cache de inicialização passa de set global para flag de instância.** O `_initialized_dbs: set[str]` no nível de módulo vira `self._initialized: bool` em cada `SqliteAuthRepository`.

---

## 3. Estrutura do pacote

```
wasp/auth/
  __init__.py            ← API pública: Protocol + shims funcionais + get_repository()
  protocol.py            ← AuthRepository (Protocol)
  sqlite_repository.py   ← SqliteAuthRepository (implementação atual)
  _schema.py             ← _DDL, init_schema (privado ao pacote)
  _connection.py         ← _connect, _resolve_db_file, _now (privado ao pacote)
```

`wasp/auth_guard.py` e `wasp/auth_cli.py` permanecem onde estão e continuam importando de `wasp.auth` exatamente como hoje.

Futuro (fora do escopo deste spec): `wasp/auth/postgres_repository.py`.

---

## 4. `AuthRepository` (Protocol)

```python
from typing import Protocol


class AuthRepository(Protocol):
    def init_schema(self) -> None: ...
    def is_authorized(self, channel: str, channel_id: str) -> str | None: ...
    def create_user(self, display_name: str) -> str: ...
    def link_identity(self, user_id: str, channel: str, channel_id: str) -> None: ...
    def create_invite(
        self,
        display_name: str,
        created_by: str,
        channel: str | None = None,
        channel_id: str | None = None,
    ) -> str: ...
    def redeem_invite(
        self, token: str, channel: str, channel_id: str
    ) -> tuple[str, str] | None: ...
    def revoke(self, channel: str, channel_id: str) -> bool: ...
    def list_identities(self) -> list[dict]: ...
    def has_any_user(self) -> bool: ...
    def bootstrap_admin(
        self, display_name: str, channel: str, channel_id: str
    ) -> str: ...
```

Renomes vs. estado atual:

- `init_db` → `init_schema` no Protocol (mais genérico, neutro a backend). O shim `auth.init_db(...)` no `__init__.py` mantém o nome antigo.

Parâmetro `db_file=` removido do contrato — configuração fica no construtor da implementação.

---

## 5. `SqliteAuthRepository`

Esqueleto:

```python
class SqliteAuthRepository:
    def __init__(self, db_file: str | None = None) -> None:
        self._db_file = _resolve_db_file(db_file)
        self._initialized = False

    def _conn(self) -> sqlite3.Connection:
        self._ensure_initialized()
        return _connect(self._db_file)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        init_schema(self._db_file)
        self._initialized = True

    # ... 10 métodos do Protocol, lógica SQL idêntica à atual
```

Pontos:

- Lógica SQL **idêntica** à atual, incluindo `BEGIN IMMEDIATE` em `redeem_invite` e `bootstrap_admin`.
- Caching de inicialização passa a ser por instância (`self._initialized`), eliminando o `_initialized_dbs` global.
- `_connect`, `_resolve_db_file`, `_now` ficam em `wasp/auth/_connection.py`.
- `_DDL` e `init_schema(db_file)` ficam em `wasp/auth/_schema.py`. `init_schema` continua idempotente.

---

## 6. `__init__.py` (API pública + shims)

```python
import os

from wasp.auth.protocol import AuthRepository
from wasp.auth.sqlite_repository import SqliteAuthRepository

__all__ = [
    "AuthRepository",
    "SqliteAuthRepository",
    "get_repository",
    "init_db",
    "is_authorized",
    "create_user",
    "link_identity",
    "create_invite",
    "redeem_invite",
    "revoke",
    "list_identities",
    "has_any_user",
    "bootstrap_admin",
]

_repository: AuthRepository | None = None


def get_repository() -> AuthRepository:
    global _repository
    if _repository is None:
        backend = os.getenv("WASP_AGENT_DB_BACKEND", "sqlite")
        if backend == "sqlite":
            _repository = SqliteAuthRepository()
        else:
            raise ValueError(f"unsupported backend: {backend}")
    return _repository


def _reset_repository() -> None:
    """Test helper: clear cached singleton."""
    global _repository
    _repository = None


def _repo(db_file: str | None) -> AuthRepository:
    return SqliteAuthRepository(db_file) if db_file else get_repository()


# Shims funcionais — preservam call sites atuais
def init_db(db_file: str | None = None) -> None:
    _repo(db_file).init_schema()


def is_authorized(channel, channel_id, db_file=None):
    return _repo(db_file).is_authorized(channel, channel_id)


def create_user(display_name, db_file=None):
    return _repo(db_file).create_user(display_name)


def link_identity(user_id, channel, channel_id, db_file=None):
    return _repo(db_file).link_identity(user_id, channel, channel_id)


def create_invite(display_name, created_by, channel=None, channel_id=None, db_file=None):
    return _repo(db_file).create_invite(display_name, created_by, channel, channel_id)


def redeem_invite(token, channel, channel_id, db_file=None):
    return _repo(db_file).redeem_invite(token, channel, channel_id)


def revoke(channel, channel_id, db_file=None):
    return _repo(db_file).revoke(channel, channel_id)


def list_identities(db_file=None):
    return _repo(db_file).list_identities()


def has_any_user(db_file=None):
    return _repo(db_file).has_any_user()


def bootstrap_admin(display_name, channel, channel_id, db_file=None):
    return _repo(db_file).bootstrap_admin(display_name, channel, channel_id)
```

Regra: quando `db_file` é passado, cria-se um repositório descartável (sem singleton). Quando `db_file is None`, usa o singleton. Isso preserva o comportamento dos testes que passam `tmp_path` explicitamente.

---

## 7. Testes

**Existentes:** `tests/test_auth.py` chama `auth.is_authorized(...)` etc. via shims — **zero mudanças necessárias**. Os testes continuam passando `db_file=tmp_path`, o que dispara o caminho de "repositório descartável" no shim.

**Novos:** `tests/test_auth_repository.py` exercita diretamente `SqliteAuthRepository(...)` (sem shim), garantindo que o Protocol está coberto sem depender do açúcar funcional.

**`tests/conftest.py`:** atualizar a lista de `sys.modules.pop` substituindo `"wasp.auth"` por:

```python
"wasp.auth",
"wasp.auth.protocol",
"wasp.auth.sqlite_repository",
"wasp.auth._schema",
"wasp.auth._connection",
```

Sem isso o estado da flag `self._initialized` e do singleton `_repository` vazam entre testes.

**`tests/e2e/conftest.py`:** o monkeypatch atual em `wasp.auth.is_authorized` continua funcionando — o shim existe.

---

## 8. Compatibilidade e impacto

- **API pública (`from wasp import auth; auth.X(...)`):** inalterada.
- **`auth_guard.py`, `auth_cli.py`, telegram, discord:** sem mudanças.
- **`init_db`:** mantido como shim. `init_schema` é o nome novo no Protocol.
- **Variável de ambiente nova:** `WASP_AGENT_DB_BACKEND` (default `sqlite`). Documentar em `docs/runbooks/auth-admin.md`.

---

## 9. Fora do escopo

- Implementação de `PostgresAuthRepository`.
- Migração de call sites para injeção explícita do repositório.
- Mudança da assinatura `list_identities() -> list[dict]` para retornar dataclasses.
- Splits do `auth_cli.py` ou refatoração do `auth_guard.py`.
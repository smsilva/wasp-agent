# Migrar callers para `auth.get_repository()` e remover shims funcionais

**Status:** Implemented  
**Data:** 2026-05-30  
**Motivação:** o refactor de `wasp/auth.py` (ver `2026-05-30-auth-repository.md`) deixou `get_repository()` como código pouco exercitado — todos os callers ainda passam pelos shims funcionais que sempre instanciam `SqliteAuthRepository` por chamada. Migrar callers para `get_repository()` e remover os shims prepara o singleton para `PostgresAuthRepository` (onde criar conexões por chamada é caro) e simplifica a superfície da API pública.

---

## 1. Contexto

Estado atual após commits `a2bdb2c`/`7589733`/`2acee2a`:

- `wasp/auth/__init__.py` expõe 10 shims funcionais (`init_db`, `is_authorized`, `create_user`, `link_identity`, `create_invite`, `redeem_invite`, `revoke`, `list_identities`, `has_any_user`, `bootstrap_admin`).
- Cada shim instancia `SqliteAuthRepository(db_file)` por chamada via `_repo()`. O singleton em `get_repository()` nunca é tocado pela API pública usada hoje.
- Em SQLite isso custa um `CREATE TABLE IF NOT EXISTS` idempotente por chamada — invisível. Em Postgres custaria abrir conexão TCP + handshake por chamada.

Callers de produção (5 arquivos):

- `main.py:22` — `auth.init_db()`
- `wasp/auth_guard.py:25` — `auth.is_authorized(channel, chat_id)`
- `wasp/auth_cli.py:55,64,72,81,89` — 5 operações administrativas
- `wasp/clients/telegram/webhook.py:71` — `auth.redeem_invite` passado como callback
- `wasp/clients/discord/bot.py:32` — `auth.is_authorized("dc", user_id)`

Testes impactados:

- `tests/test_auth.py` — 44 ocorrências de `auth.X(..., db_file=db_file)` (cobertura duplicada com `test_auth_repository.py`)
- `tests/test_auth_cli.py` — 15 ocorrências sem `db_file=`
- `tests/test_auth_guard.py` — 3 monkeypatches em `wasp.auth.is_authorized`
- `tests/test_provision.py` — 10 monkeypatches em `wasp.auth.is_authorized`
- `tests/test_main.py` — 1 monkeypatch em `wasp.auth.init_db`
- `tests/e2e/conftest.py` — 1 monkeypatch em `wasp.auth.is_authorized`

---

## 2. Decisões de design

**Remover os 10 shims.** `get_repository()` vira o único entrypoint público para operações de auth.

**Singleton via `get_repository()` permanece** como hoje (cacheado em variável de módulo, `_reset_repository()` exposto para testes).

**`tests/test_auth.py` é deletado** — sua cobertura está duplicada em `tests/test_auth_repository.py`, que exercita `SqliteAuthRepository` diretamente. Manter os dois mantém duplicação sem ganho.

**Testes com monkeypatch passam a patchar a instância**, não o módulo. Pattern:

```python
from wasp import auth
repo = auth.get_repository()
monkeypatch.setattr(repo, "is_authorized", lambda c, i: "user-abc")
```

Isso depende do `_reset_repository()` do `mock_agno` (já presente) — cada teste começa com singleton limpo.

---

## 3. Mudanças nos callers de produção

### `main.py:22`

```python
# antes
auth.init_db()
# depois
auth.get_repository().init_schema()
```

### `wasp/auth_guard.py:25`

```python
# antes
user_id = auth.is_authorized(channel, chat_id) if chat_id else None
# depois
user_id = auth.get_repository().is_authorized(channel, chat_id) if chat_id else None
```

### `wasp/auth_cli.py`

```python
def main(argv=None):
    ...
    args = parser.parse_args(argv)
    repo = auth.get_repository()

    if args.cmd == "bootstrap":
        try:
            user_id = repo.bootstrap_admin(args.name, args.channel, args.channel_id)
        ...
    if args.cmd == "link":
        repo.link_identity(args.user_id, args.channel, args.channel_id)
        ...
    # 5 operações no total
```

### `wasp/clients/telegram/webhook.py:71`

```python
# antes
handled = await _process_start_token(
    body, auth.redeem_invite, notifier.send
)
# depois
handled = await _process_start_token(
    body, lambda *a: auth.get_repository().redeem_invite(*a), notifier.send
)
```

Lambda resolve `get_repository()` no momento da chamada (lazy), evitando que o callback fique bound a uma instância antiga caso `_reset_repository()` seja invocado depois (em testes, principalmente).

### `wasp/clients/discord/bot.py:32`

```python
# antes
if auth.is_authorized("dc", user_id) is None:
# depois
if auth.get_repository().is_authorized("dc", user_id) is None:
```

---

## 4. Limpeza em `wasp/auth/__init__.py`

Versão final:

```python
import os

from wasp.auth.protocol import AuthRepository as AuthRepository
from wasp.auth.sqlite_repository import SqliteAuthRepository as SqliteAuthRepository

__all__ = ["AuthRepository", "SqliteAuthRepository", "get_repository"]

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
    global _repository
    _repository = None
```

Removidos: `_repo` e os 10 shims.

`init_db` (alias para `init_schema`) deixa de existir. Quem chama `init_db` no Protocol não existe — só era nome no shim.

---

## 5. Mudanças nos testes

### `tests/test_auth.py` — DELETAR

Cobertura duplicada com `tests/test_auth_repository.py`. Antes de deletar, confirmar paridade caso a caso e migrar qualquer teste único que não esteja em `test_auth_repository.py`.

### `tests/test_auth_cli.py` — atualizar verificações

Substituir `auth.X(...)` (sem `db_file=`) por `auth.get_repository().X(...)`. A fixture autouse `_db_isolation` que seta `WASP_AGENT_DB_FILE` continua válida — `get_repository()` resolve env no momento da chamada, e `_reset_repository()` no `mock_agno` garante singleton limpo entre testes.

### `tests/test_auth_guard.py` — patchar instância

Pattern novo:

```python
def test_guard_authorizes_known_tg_user(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard
    from wasp import auth

    repo = auth.get_repository()
    monkeypatch.setattr(repo, "is_authorized", lambda c, i: "user-abc")
    ...
```

3 testes (`test_guard_authorizes_known_tg_user`, `test_guard_denies_unknown_tg_user`, `test_guard_denies_when_chat_id_missing`).

### `tests/test_provision.py` — patchar instância

Mesmo pattern. 10 testes.

### `tests/test_main.py` — patchar instância

```python
# antes
monkeypatch.setattr("wasp.auth.init_db", lambda db_file=None: init_called.append(db_file))
# depois
from wasp import auth
repo = auth.get_repository()
monkeypatch.setattr(repo, "init_schema", lambda: init_called.append(None))
```

### `tests/e2e/conftest.py` — patchar instância

```python
# antes
monkeypatch.setattr(wasp.auth, "is_authorized", lambda *a, **kw: "fake-user")
# depois
repo = wasp.auth.get_repository()
monkeypatch.setattr(repo, "is_authorized", lambda *a, **kw: "fake-user")
```

---

## 6. Validação

Após cada bloco de mudanças, rodar:

```bash
make format
make test
```

E ao final, antes de mergear:

```bash
make e2e-with-debug
```

Coverage deve permanecer 100%. Se algum branch ficar descoberto após deletar `test_auth.py`, é sinal de que `test_auth_repository.py` perdeu cobertura — completar lá.

---

## 7. Implicações para Postgres futuro

Após o refactor:

- `get_repository()` é o único entrypoint público.
- Adicionar Postgres: criar `wasp/auth/postgres_repository.py` implementando o Protocol (pool de conexões no `__init__`); adicionar branch `elif backend == "postgres":` em `get_repository()`.
- Callers não mudam — `auth.get_repository().is_authorized(...)` continua funcionando.
- Singleton garante uma única criação de pool por processo.

---

## 8. Riscos

- **Monkeypatch via instância depende de `get_repository()` ser chamado dos dois lados.** Se o caller invocar `get_repository()` antes do teste fixar o patch na instância correta, o caller usa o método original. Mitigação: `mock_agno` faz `_reset_repository()` no setup, garantindo que o primeiro `get_repository()` dentro do teste cria a instância nova; o monkeypatch em seguida atinge essa mesma instância (singleton).
- ~~`webhook.py` captura `auth.get_repository().redeem_invite` como callback~~ — mitigado via lambda lazy (ver §3).
- **`auth_cli.py` em um worker de longa duração** — não é o caso (CLI é one-shot). Cada invocação do CLI cria seu próprio singleton.

---

## 9. Fora do escopo

- Implementação de `PostgresAuthRepository`.
- Migração para injeção explícita do repositório nos construtores dos callers (alternativa mais Pythonic, custo maior, deixada para depois).
- Refatoração do `auth_guard.py` ou `auth_cli.py` além do necessário para usar `get_repository()`.

---

## 10. Plano de execução resumido

Etapas mutáveis em ordem (cada etapa fecha verde):

1. Atualizar `auth_guard.py`, `auth_cli.py`, `webhook.py`, `bot.py`, `main.py` para `get_repository()`.
2. Atualizar testes que monkeypatcham (`test_auth_guard.py`, `test_provision.py`, `test_main.py`, `tests/e2e/conftest.py`).
3. Atualizar `test_auth_cli.py` (verificações via `get_repository()`).
4. Confirmar paridade de cobertura entre `test_auth.py` e `test_auth_repository.py`; migrar testes únicos.
5. Deletar `test_auth.py`.
6. Remover shims de `wasp/auth/__init__.py` (deixa só `get_repository`, `_reset_repository`, exports).
7. `make format && make test && make e2e-with-debug`.

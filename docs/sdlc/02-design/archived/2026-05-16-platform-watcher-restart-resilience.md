# Watcher restart resilience

**Date:** 2026-05-16  
**Updated:** 2026-06-03  
**Status:** Draft

## Contexto

O agente possui watchers in-process (`threading.Thread` + `asyncio.run`) que observam CRDs
(`Platform`, `Cluster`) e notificam o usuário quando `Ready: True`.

No MVP, watches são puramente in-memory: se o processo cair antes de o CRD ficar Ready,
a notificação é perdida. Este design resolve isso via persistência em banco de dados.

## Escopo

Cobrir qualquer CRD monitorável (genérico via coluna `kind`) — não apenas Platform.
Inclui a migração do acesso a dados do auth para SQLAlchemy Core, unificando a camada
de banco do projeto.

## Fora de escopo

- Retentativas de notificação se a API do canal (Telegram, Discord) falhar
- Limpeza de watches antigos (`status != pending` há > N dias)
- Migrações de schema (usar `create_all(checkfirst=True)` no startup)

## Arquitetura

### `wasp/db/` — engine compartilhado

Engine SQLAlchemy único para todo o sistema. Backend controlado por `DATABASE_BACKEND`.

```
wasp/db/
  __init__.py    ← get_engine() singleton
```

```python
def get_engine() -> Engine:
    backend = os.getenv("DATABASE_BACKEND", "sqlite")
    if backend == "sqlite":
        db_file = os.getenv("DATABASE_FILE", "agent.db")
        return create_engine(
            f"sqlite:///{db_file}",
            poolclass=NullPool,
            connect_args={"check_same_thread": False},
        )
    return create_engine(os.getenv("DATABASE_URL"))
```

Quando `DATABASE_BACKEND=sqlite`, tudo usa SQLite.
Quando `DATABASE_BACKEND=postgres`, tudo usa Postgres. Sem engines paralelos.

### `wasp/auth/` — migração para SQLAlchemy Core

`_connection.py` é removido. `sqlite_repository.py` e `postgres_repository.py` são
substituídos por um único `repository.py` que usa `wasp.db.get_engine()`.

```
wasp/auth/
  __init__.py          ← get_repository() sem if/else de backend
  protocol.py          ← sem mudança
  repository.py        ← novo, SQLAlchemy Core
  _schema.py           ← metadata.create_all(get_engine())
  # _connection.py       ← REMOVIDO
  # sqlite_repository.py  ← REMOVIDO
  # postgres_repository.py ← REMOVIDO
```

Operações simples usam `with engine.begin() as conn: conn.execute(text(...))`.

Operações de check-then-write (concorrência crítica) usam SQL específico de dialeto
restrito a dois métodos:

| Método | SQLite | Postgres |
|---|---|---|
| `redeem_invite` | `BEGIN IMMEDIATE` via `text()` | `SELECT ... FOR UPDATE` |
| `bootstrap_admin` | `BEGIN IMMEDIATE` via `text()` | `LOCK TABLE ... IN ACCESS EXCLUSIVE` |

Detecção via `engine.dialect.name` (`"sqlite"` ou `"postgresql"`).

### `wasp/watches/` — persistência de watches

```
wasp/watches/
  __init__.py      ← get_repository() singleton + restore_pending_watches()
  _schema.py       ← Table resource_watches + init_schema()
  repository.py    ← WatchRepository
```

#### Tabela `resource_watches`

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK autoincrement | — |
| `kind` | TEXT NOT NULL | `"Platform"`, `"Cluster"`, etc. |
| `name` | TEXT NOT NULL | nome do CRD |
| `session_id` | TEXT NOT NULL | `tg:entity:chat_id` — destino da notificação |
| `status` | TEXT NOT NULL | `pending` \| `ready` \| `failed` \| `timeout` |
| `created_at` | TEXT NOT NULL | ISO 8601 UTC |
| `notified_at` | TEXT NULL | preenchido ao enviar notificação |

UNIQUE constraint em `(kind, name)` para evitar watches duplicados.

#### `WatchRepository`

```python
def register(kind, name, session_id) -> None   # INSERT, ignora conflito
def complete(kind, name) -> None               # UPDATE status=ready, notified_at=now
def fail(kind, name) -> None                   # UPDATE status=failed
def timeout(kind, name) -> None                # UPDATE status=timeout
def list_pending() -> list[dict]               # SELECT WHERE status=pending
```

`register` usa `try/except IntegrityError` para idempotência (funciona em SQLite e Postgres).

### Spawners — integração com persistência

`PlatformWatcherSpawner.spawn` e `ClusterWatcherSpawner.spawn`:

1. `get_repository().register(kind, name, session_id)` — antes de spawnar a thread
2. `threading.Thread(target=_run_watcher, daemon=True).start()`

Dentro de `watch_platform` / `watch_cluster`, ao terminar:

- Ready → `get_repository().complete(kind, name)` → enviar notificação
- Timeout → `get_repository().timeout(kind, name)` → enviar aviso
- Exceção não recuperável → `get_repository().fail(kind, name)`

Ordem importa: `complete()` antes de `notifier.send()` garante que, em caso de crash
entre os dois, o próximo startup não re-notifica (at-most-once na prática).

### Recovery no startup

Em `main.py`, após `create_app()` (canais precisam estar registrados):

```python
from wasp.watches import restore_pending_watches
restore_pending_watches()
```

`restore_pending_watches()`:

1. `list_pending()` — busca watches com `status=pending`
2. Para cada linha:
   - Extrai `channel` do `session_id` via `extract_channel`
   - Reconstrói notifier via `_select_notifier(channel)`
   - Spawna novo thread de watch
3. Se o CRD não existe (404 imediato): watcher chama `fail()` e encerra

## Garantias

- **At-most-once de notificação:** `complete()` grava antes de `notifier.send()`. Se o
  processo cair entre os dois, o watch some da lista de pending e a notificação não é
  reenviada no próximo startup.
- **Idempotência de `register`:** INSERT com `ON CONFLICT DO NOTHING` — spawnar o mesmo
  watch duas vezes não cria duplicatas.

## Riscos

- Race condition entre `register()` e `threading.Thread.start()`: mitigado fazendo
  `register` antes do `start`. Se o processo cair entre os dois, o watch é restaurado
  no próximo startup.
- Crescimento da tabela: aceitar no MVP. `status != pending` pode ser limpo por job
  separado se passar de ~10k linhas.
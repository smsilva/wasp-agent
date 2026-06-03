# Watcher Restart Resilience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist active watches to the database and replay them on agent restart, using a shared SQLAlchemy engine that works for both SQLite and Postgres.

**Architecture:** Introduce `wasp/db/` as a shared SQLAlchemy engine layer used by both `wasp/auth/` (migrated from raw sqlite3/psycopg3) and a new `wasp/watches/` package that persists CRD watch state. Spawners register watches before threading; watch coroutines mark them complete/failed/timed-out. `main.py` restores pending watches after channels are registered.

**Tech Stack:** SQLAlchemy 2.0 Core (already in `pyproject.toml`), SQLite (NullPool), Postgres (default pool), pytest, testcontainers.

---

## File Map

| Action | File |
|---|---|
| Create | `wasp/db/__init__.py` |
| Create | `wasp/auth/repository.py` |
| Modify | `wasp/auth/_schema.py` |
| Modify | `wasp/auth/__init__.py` |
| Delete | `wasp/auth/_connection.py` |
| Delete | `wasp/auth/sqlite_repository.py` |
| Delete | `wasp/auth/postgres_repository.py` |
| Create | `wasp/watches/__init__.py` |
| Create | `wasp/watches/_schema.py` |
| Create | `wasp/watches/repository.py` |
| Modify | `wasp/watcher.py` |
| Modify | `wasp/resources/platform/provisioner.py` |
| Modify | `wasp/resources/cluster/provisioner.py` |
| Modify | `main.py` |
| Modify | `tests/conftest.py` |
| Modify | `tests/test_auth_repository.py` |
| Modify | `tests/test_postgres_auth_repository.py` |
| Create | `tests/test_watches_repository.py` |
| Create | `tests/test_watches_restore.py` |

---

## Task 1: `wasp/db/__init__.py` — shared engine singleton

**Files:**
- Create: `wasp/db/__init__.py`
- Create: `tests/test_db_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_engine.py
import pytest


def test_get_engine_sqlite_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "test.db"))
    from wasp.db import _reset_engine, get_engine
    _reset_engine()
    engine = get_engine()
    assert "sqlite" in str(engine.url)
    assert "test.db" in str(engine.url)
    _reset_engine()


def test_get_engine_returns_singleton(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "s.db"))
    from wasp.db import _reset_engine, get_engine
    _reset_engine()
    a = get_engine()
    b = get_engine()
    assert a is b
    _reset_engine()


def test_get_engine_postgres_uses_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    from wasp.db import _reset_engine, get_engine
    _reset_engine()
    engine = get_engine()
    assert "postgresql" in str(engine.url)
    _reset_engine()


def test_get_engine_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "mongo")
    from wasp.db import _reset_engine, get_engine
    _reset_engine()
    with pytest.raises(ValueError, match="unsupported"):
        get_engine()
    _reset_engine()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db_engine.py -v
```

Expected: `ModuleNotFoundError: No module named 'wasp.db'`

- [ ] **Step 3: Implement `wasp/db/__init__.py`**

```python
import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def _reset_engine() -> None:
    global _engine
    _engine = None


def _build_engine() -> Engine:
    backend = os.getenv("DATABASE_BACKEND", "sqlite")
    if backend == "sqlite":
        db_file = os.getenv("DATABASE_FILE", "agent.db")
        return create_engine(
            f"sqlite:///{db_file}",
            poolclass=NullPool,
            connect_args={"check_same_thread": False},
        )
    if backend == "postgres":
        url = os.environ["DATABASE_URL"]
        return create_engine(url)
    raise ValueError(f"unsupported DATABASE_BACKEND: {backend}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db_engine.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Add `wasp.db` to the module eviction list in `tests/conftest.py`**

In both the setup and teardown loops inside `mock_agno`, add:
```python
"wasp.db",
```
after `"wasp.startup"`.

- [ ] **Step 6: Commit**

```bash
git add wasp/db/__init__.py tests/test_db_engine.py tests/conftest.py
git commit -m "feat(db): add shared SQLAlchemy engine singleton"
```

---

## Task 2: Migrate `wasp/auth/_schema.py` to SQLAlchemy MetaData

**Files:**
- Modify: `wasp/auth/_schema.py`

- [ ] **Step 1: Write a test for the new `init_schema` signature**

Add to `tests/test_auth_repository.py` (at the top, before existing tests):

```python
def test_init_schema_creates_three_tables_via_engine(tmp_path):
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.pool import NullPool
    engine = create_engine(
        f"sqlite:///{tmp_path / 'schema.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    from wasp.auth._schema import init_schema
    init_schema(engine)
    names = inspect(engine).get_table_names()
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_auth_repository.py::test_init_schema_creates_three_tables_via_engine -v
```

Expected: FAIL — current `init_schema` takes a `db_file: str`, not an engine.

- [ ] **Step 3: Replace `wasp/auth/_schema.py` entirely**

```python
from sqlalchemy import Engine, ForeignKey, Index, MetaData, Table
from sqlalchemy import Column, Text

metadata = MetaData()

auth_users = Table(
    "auth_users",
    metadata,
    Column("user_id", Text, primary_key=True),
    Column("display_name", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

auth_identities = Table(
    "auth_identities",
    metadata,
    Column("channel", Text, nullable=False, primary_key=True),
    Column("channel_id", Text, nullable=False, primary_key=True),
    Column("user_id", Text, ForeignKey("auth_users.user_id"), nullable=False),
    Column("linked_at", Text, nullable=False),
)

Index("auth_identities_user_idx", auth_identities.c.user_id)

auth_invites = Table(
    "auth_invites",
    metadata,
    Column("token", Text, primary_key=True),
    Column("user_id", Text, ForeignKey("auth_users.user_id"), nullable=False),
    Column("channel", Text),
    Column("channel_id", Text),
    Column("created_by", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    Column("used_at", Text),
)


def init_schema(engine: Engine) -> None:
    metadata.create_all(engine)
```

- [ ] **Step 4: Run tests to verify**

```bash
pytest tests/test_auth_repository.py::test_init_schema_creates_three_tables_via_engine -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add wasp/auth/_schema.py tests/test_auth_repository.py
git commit -m "refactor(auth): migrate _schema to SQLAlchemy MetaData"
```

---

## Task 3: `wasp/auth/repository.py` — simple methods

Create the new unified auth repository. The class takes an optional `engine` parameter to allow test isolation without env var patching.

**Files:**
- Create: `wasp/auth/repository.py`

- [ ] **Step 1: Write failing tests**

Replace `tests/test_auth_repository.py` entirely with the following. This changes the fixture (no more `SqliteAuthRepository(db_file)`) and removes tests that rely on the old class API:

```python
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
def engine(tmp_path):
    e = create_engine(
        f"sqlite:///{tmp_path / 'agent.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    yield e
    e.dispose()


@pytest.fixture
def repo(engine):
    from wasp.auth.repository import AuthRepository
    r = AuthRepository(engine=engine)
    r.init_schema()
    return r


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "agent.db"


def test_init_schema_creates_three_tables_via_engine(tmp_path):
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.pool import NullPool
    e = create_engine(
        f"sqlite:///{tmp_path / 'schema.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    from wasp.auth._schema import init_schema
    init_schema(e)
    names = inspect(e).get_table_names()
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names


def test_init_schema_is_idempotent(repo):
    repo.init_schema()
    repo.init_schema()


def test_is_authorized_returns_none_for_unknown(repo):
    assert repo.is_authorized("tg", "12345") is None


def test_create_user_and_link_identity(repo):
    user_id = repo.create_user("Alice")
    assert isinstance(user_id, str) and len(user_id) == 32
    repo.link_identity(user_id, "tg", "12345")
    assert repo.is_authorized("tg", "12345") == user_id


def test_has_any_user_false_then_true(repo):
    assert repo.has_any_user() is False
    repo.create_user("Alice")
    assert repo.has_any_user() is True


def test_create_invite_returns_urlsafe_token(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    assert isinstance(token, str) and len(token) >= 40


def test_revoke_removes_identity_keeps_user(repo):
    user_id = repo.create_user("Alice")
    repo.link_identity(user_id, "tg", "12345")
    assert repo.revoke("tg", "12345") is True
    assert repo.is_authorized("tg", "12345") is None


def test_revoke_returns_false_when_not_found(repo):
    assert repo.revoke("tg", "missing") is False


def test_list_identities_returns_dicts(repo):
    user_id = repo.create_user("Alice")
    repo.link_identity(user_id, "tg", "12345")
    rows = repo.list_identities()
    assert len(rows) == 1
    assert rows[0] == {
        "channel": "tg",
        "channel_id": "12345",
        "user_id": user_id,
        "display_name": "Alice",
        "linked_at": rows[0]["linked_at"],
    }


def test_create_user_persists_display_name(engine, tmp_path):
    from wasp.auth.repository import AuthRepository
    repo = AuthRepository(engine=engine)
    repo.init_schema()
    user_id = repo.create_user("Alice")
    con = sqlite3.connect(str(tmp_path / "agent.db"))
    try:
        row = con.execute(
            "SELECT display_name FROM auth_users WHERE user_id=?", (user_id,)
        ).fetchone()
    finally:
        con.close()
    assert row[0] == "Alice"


def test_create_invite_default_ttl_is_one_hour(repo, tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_INVITE_TTL_HOURS", raising=False)
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    con = sqlite3.connect(str(tmp_path / "agent.db"))
    try:
        row = con.execute(
            "SELECT created_at, expires_at FROM auth_invites WHERE token=?", (token,)
        ).fetchone()
    finally:
        con.close()
    assert datetime.fromisoformat(row[1]) - datetime.fromisoformat(row[0]) == timedelta(hours=1)


def test_create_invite_uses_env_ttl(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_INVITE_TTL_HOURS", "5")
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    con = sqlite3.connect(str(tmp_path / "agent.db"))
    try:
        row = con.execute(
            "SELECT created_at, expires_at FROM auth_invites WHERE token=?", (token,)
        ).fetchone()
    finally:
        con.close()
    assert datetime.fromisoformat(row[1]) - datetime.fromisoformat(row[0]) == timedelta(hours=5)


def test_get_repository_returns_singleton(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "singleton.db"))
    from wasp import auth
    from wasp.db import _reset_engine
    auth._reset_repository()
    _reset_engine()
    a = auth.get_repository()
    b = auth.get_repository()
    assert a is b
    auth._reset_repository()
    _reset_engine()


def test_get_repository_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "mongo")
    from wasp import auth
    from wasp.db import _reset_engine
    auth._reset_repository()
    _reset_engine()
    with pytest.raises(ValueError, match="unsupported"):
        auth.get_repository()
    auth._reset_repository()
    _reset_engine()


def test_db_file_defaults_to_env_var(tmp_path, monkeypatch):
    target = str(tmp_path / "from_env.db")
    monkeypatch.setenv("DATABASE_FILE", target)
    from wasp.db import _reset_engine, get_engine
    _reset_engine()
    from wasp.auth.repository import AuthRepository
    repo = AuthRepository()
    repo.init_schema()
    assert repo.has_any_user() is False
    user_id = repo.create_user("Alice")
    repo.link_identity(user_id, "tg", "1")
    assert repo.is_authorized("tg", "1") == user_id
    _reset_engine()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_auth_repository.py -v -k "not redeem and not bootstrap and not concurrent"
```

Expected: `ImportError: cannot import name 'AuthRepository' from 'wasp.auth.repository'`

- [ ] **Step 3: Create `wasp/auth/repository.py` with simple methods only**

```python
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, text

from wasp.db import get_engine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuthRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else get_engine()

    def init_schema(self) -> None:
        from wasp.auth._schema import init_schema as _init_schema
        _init_schema(self._engine)

    def is_authorized(self, channel: str, channel_id: str) -> str | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT user_id FROM auth_identities "
                    "WHERE channel=:channel AND channel_id=:channel_id"
                ),
                {"channel": channel, "channel_id": channel_id},
            ).one_or_none()
            return row[0] if row else None

    def create_user(self, display_name: str) -> str:
        user_id = uuid.uuid4().hex
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO auth_users (user_id, display_name, created_at) "
                    "VALUES (:user_id, :display_name, :created_at)"
                ),
                {"user_id": user_id, "display_name": display_name, "created_at": _now()},
            )
        return user_id

    def link_identity(self, user_id: str, channel: str, channel_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                    "VALUES (:channel, :channel_id, :user_id, :linked_at)"
                ),
                {"channel": channel, "channel_id": channel_id, "user_id": user_id, "linked_at": _now()},
            )

    def has_any_user(self) -> bool:
        with self._engine.connect() as conn:
            return conn.execute(text("SELECT 1 FROM auth_users LIMIT 1")).one_or_none() is not None

    def create_invite(
        self,
        display_name: str,
        created_by: str,
        channel: str | None = None,
        channel_id: str | None = None,
    ) -> str:
        ttl_hours = int(os.getenv("AGENT_INVITE_TTL_HOURS", "1"))
        user_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO auth_users (user_id, display_name, created_at) "
                    "VALUES (:user_id, :display_name, :created_at)"
                ),
                {"user_id": user_id, "display_name": display_name, "created_at": created_at},
            )
            conn.execute(
                text(
                    "INSERT INTO auth_invites "
                    "(token, user_id, channel, channel_id, created_by, created_at, expires_at, used_at) "
                    "VALUES (:token, :user_id, :channel, :channel_id, :created_by, "
                    ":created_at, :expires_at, NULL)"
                ),
                {
                    "token": token,
                    "user_id": user_id,
                    "channel": channel,
                    "channel_id": channel_id,
                    "created_by": created_by,
                    "created_at": created_at,
                    "expires_at": expires_at,
                },
            )
        return token

    def revoke(self, channel: str, channel_id: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM auth_identities "
                    "WHERE channel=:channel AND channel_id=:channel_id"
                ),
                {"channel": channel, "channel_id": channel_id},
            )
            return result.rowcount > 0

    def list_identities(self) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT i.channel, i.channel_id, i.user_id, u.display_name, i.linked_at "
                    "FROM auth_identities i "
                    "JOIN auth_users u ON u.user_id = i.user_id "
                    "ORDER BY i.linked_at"
                )
            ).fetchall()
        return [
            {
                "channel": r[0],
                "channel_id": r[1],
                "user_id": r[2],
                "display_name": r[3],
                "linked_at": r[4],
            }
            for r in rows
        ]

    def redeem_invite(  # pragma: no cover — implemented in Task 4
        self, token: str, channel: str, channel_id: str
    ) -> tuple[str, str] | None:
        raise NotImplementedError

    def bootstrap_admin(  # pragma: no cover — implemented in Task 4
        self, display_name: str, channel: str, channel_id: str
    ) -> str:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests (excluding redeem/bootstrap) to verify they pass**

```bash
pytest tests/test_auth_repository.py -v -k "not redeem and not bootstrap and not concurrent"
```

Expected: all targeted tests PASS

- [ ] **Step 5: Commit**

```bash
git add wasp/auth/repository.py tests/test_auth_repository.py
git commit -m "feat(auth): add AuthRepository with SQLAlchemy Core (simple methods)"
```

---

## Task 4: `wasp/auth/repository.py` — dialect-specific methods

Implement `redeem_invite` and `bootstrap_admin` with dialect-aware locking.

**Files:**
- Modify: `wasp/auth/repository.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_auth_repository.py`:

```python
def test_redeem_invite_creates_identity_and_returns_user(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    result = repo.redeem_invite(token, "tg", "67890")
    assert result is not None
    user_id, display_name = result
    assert display_name == "Bob"
    assert repo.is_authorized("tg", "67890") == user_id


def test_redeem_invite_returns_none_for_unknown_token(repo):
    assert repo.redeem_invite("nonexistent", "tg", "1") is None


def test_redeem_invite_returns_none_when_expired(repo, tmp_path):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    con = sqlite3.connect(str(tmp_path / "agent.db"))
    try:
        con.execute("UPDATE auth_invites SET expires_at=? WHERE token=?", (past, token))
        con.commit()
    finally:
        con.close()
    assert repo.redeem_invite(token, "tg", "67890") is None


def test_redeem_invite_returns_none_when_already_consumed(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    assert repo.redeem_invite(token, "tg", "67890") is not None
    assert repo.redeem_invite(token, "tg", "11111") is None


def test_redeem_invite_rejects_channel_mismatch(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin, channel="tg", channel_id="67890")
    assert repo.redeem_invite(token, "discord", "67890") is None
    assert repo.redeem_invite(token, "tg", "00000") is None
    assert repo.redeem_invite(token, "tg", "67890") is not None


def test_redeem_invite_rejects_when_identity_already_linked(repo, tmp_path):
    user1 = repo.create_user("Existing")
    repo.link_identity(user1, "tg", "111")
    token = repo.create_invite("New", created_by=user1)
    assert repo.redeem_invite(token, "tg", "111") is None
    con = sqlite3.connect(str(tmp_path / "agent.db"))
    try:
        used_at = con.execute(
            "SELECT used_at FROM auth_invites WHERE token=?", (token,)
        ).fetchone()[0]
    finally:
        con.close()
    assert used_at is None


def test_bootstrap_creates_first_user_when_db_empty(repo):
    user_id = repo.bootstrap_admin("Silvio", "tg", "12345678")
    assert user_id
    assert repo.is_authorized("tg", "12345678") == user_id


def test_bootstrap_fails_when_db_not_empty(repo):
    repo.create_user("First")
    with pytest.raises(RuntimeError, match="not empty"):
        repo.bootstrap_admin("Silvio", "tg", "12345678")


def test_redeem_invite_concurrent_unbound_token_only_succeeds_once(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    results = []
    errors = []
    barrier = threading.Barrier(2)

    def redeem(channel_id):
        try:
            barrier.wait()
            results.append(repo.redeem_invite(token, "tg", channel_id))
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=redeem, args=("111",))
    t2 = threading.Thread(target=redeem, args=("222",))
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert not errors
    assert len([r for r in results if r is not None]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_auth_repository.py -v -k "redeem or bootstrap or concurrent"
```

Expected: FAIL — `NotImplementedError`

- [ ] **Step 3: Replace the two stub methods in `wasp/auth/repository.py`**

Remove the `# pragma: no cover` stubs and add the full implementations:

```python
    def redeem_invite(
        self, token: str, channel: str, channel_id: str
    ) -> tuple[str, str] | None:
        dialect = self._engine.dialect.name
        if dialect == "sqlite":
            conn_ctx = self._engine.connect().execution_options(isolation_level="IMMEDIATE")
            select_q = (
                "SELECT user_id, channel, channel_id, expires_at, used_at "
                "FROM auth_invites WHERE token=:token"
            )
        else:
            conn_ctx = self._engine.connect()
            select_q = (
                "SELECT user_id, channel, channel_id, expires_at, used_at "
                "FROM auth_invites WHERE token=:token FOR UPDATE"
            )
        with conn_ctx as conn:
            row = conn.execute(text(select_q), {"token": token}).one_or_none()
            if row is None:
                return None
            user_id, bound_channel, bound_channel_id, expires_at, used_at = row
            if used_at is not None:
                return None
            if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                return None
            if bound_channel is not None and bound_channel != channel:
                return None
            if bound_channel_id is not None and bound_channel_id != channel_id:
                return None
            already = conn.execute(
                text(
                    "SELECT 1 FROM auth_identities "
                    "WHERE channel=:channel AND channel_id=:channel_id"
                ),
                {"channel": channel, "channel_id": channel_id},
            ).one_or_none()
            if already is not None:
                return None
            now = _now()
            conn.execute(
                text(
                    "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                    "VALUES (:channel, :channel_id, :user_id, :linked_at)"
                ),
                {"channel": channel, "channel_id": channel_id, "user_id": user_id, "linked_at": now},
            )
            conn.execute(
                text("UPDATE auth_invites SET used_at=:now WHERE token=:token"),
                {"now": now, "token": token},
            )
            display_name = conn.execute(
                text("SELECT display_name FROM auth_users WHERE user_id=:user_id"),
                {"user_id": user_id},
            ).scalar_one()
            conn.commit()
            return (user_id, display_name)

    def bootstrap_admin(self, display_name: str, channel: str, channel_id: str) -> str:
        dialect = self._engine.dialect.name
        if dialect == "sqlite":
            conn_ctx = self._engine.connect().execution_options(isolation_level="IMMEDIATE")
        else:
            conn_ctx = self._engine.connect()
        with conn_ctx as conn:
            if dialect == "postgresql":
                conn.execute(text("LOCK TABLE auth_users IN ACCESS EXCLUSIVE MODE"))
            if conn.execute(text("SELECT 1 FROM auth_users LIMIT 1")).one_or_none() is not None:
                raise RuntimeError("auth tables not empty — bootstrap refused")
            user_id = uuid.uuid4().hex
            now = _now()
            conn.execute(
                text(
                    "INSERT INTO auth_users (user_id, display_name, created_at) "
                    "VALUES (:user_id, :display_name, :created_at)"
                ),
                {"user_id": user_id, "display_name": display_name, "created_at": now},
            )
            conn.execute(
                text(
                    "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                    "VALUES (:channel, :channel_id, :user_id, :linked_at)"
                ),
                {"channel": channel, "channel_id": channel_id, "user_id": user_id, "linked_at": now},
            )
            conn.commit()
            return user_id
```

- [ ] **Step 4: Run all auth tests to verify they pass**

```bash
pytest tests/test_auth_repository.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add wasp/auth/repository.py tests/test_auth_repository.py
git commit -m "feat(auth): implement redeem_invite and bootstrap_admin with dialect locking"
```

---

## Task 5: Wire auth — update `__init__.py`, delete old files, update postgres tests

**Files:**
- Modify: `wasp/auth/__init__.py`
- Modify: `tests/test_postgres_auth_repository.py`
- Modify: `tests/conftest.py`
- Delete: `wasp/auth/_connection.py`, `wasp/auth/sqlite_repository.py`, `wasp/auth/postgres_repository.py`

- [ ] **Step 1: Replace `wasp/auth/__init__.py`**

```python
from wasp.auth.protocol import AuthRepository as AuthRepository

__all__ = ["AuthRepository", "get_repository"]

_repository = None


def get_repository():
    global _repository
    if _repository is None:
        from wasp.auth.repository import AuthRepository as _AuthRepository
        r = _AuthRepository()
        r.init_schema()
        _repository = r
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None
```

- [ ] **Step 2: Update `tests/test_postgres_auth_repository.py`**

Replace the file entirely. The repo now uses SQLAlchemy with a Postgres engine:

```python
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url(driver=None)


@pytest.fixture(scope="session")
def pg_engine(pg_url):
    engine = create_engine(pg_url)
    yield engine
    engine.dispose()


@pytest.fixture
def repo(pg_engine):
    from wasp.auth.repository import AuthRepository
    r = AuthRepository(engine=pg_engine)
    r.init_schema()
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE auth_invites, auth_identities, auth_users CASCADE"))
    return r


def test_init_schema_creates_three_tables(repo, pg_engine):
    from sqlalchemy import inspect
    names = inspect(pg_engine).get_table_names()
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names


def test_init_schema_is_idempotent(repo):
    repo.init_schema()


def test_is_authorized_returns_none_for_unknown(repo):
    assert repo.is_authorized("tg", "12345") is None


def test_create_user_and_link_identity(repo):
    user_id = repo.create_user("Alice")
    assert isinstance(user_id, str) and len(user_id) == 32
    repo.link_identity(user_id, "tg", "12345")
    assert repo.is_authorized("tg", "12345") == user_id


def test_has_any_user_false_then_true(repo):
    assert repo.has_any_user() is False
    repo.create_user("Alice")
    assert repo.has_any_user() is True


def test_create_invite_returns_urlsafe_token(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    assert isinstance(token, str) and len(token) >= 40


def test_redeem_invite_creates_identity_and_returns_user(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    result = repo.redeem_invite(token, "tg", "67890")
    assert result is not None
    user_id, display_name = result
    assert display_name == "Bob"
    assert repo.is_authorized("tg", "67890") == user_id


def test_redeem_invite_returns_none_for_unknown_token(repo):
    assert repo.redeem_invite("nonexistent", "tg", "1") is None


def test_redeem_invite_returns_none_when_expired(repo, pg_engine):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with pg_engine.begin() as conn:
        conn.execute(
            text("UPDATE auth_invites SET expires_at=:past WHERE token=:token"),
            {"past": past, "token": token},
        )
    assert repo.redeem_invite(token, "tg", "67890") is None


def test_redeem_invite_returns_none_when_already_consumed(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    assert repo.redeem_invite(token, "tg", "67890") is not None
    assert repo.redeem_invite(token, "tg", "11111") is None


def test_redeem_invite_rejects_channel_mismatch(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin, channel="tg", channel_id="67890")
    assert repo.redeem_invite(token, "discord", "67890") is None
    assert repo.redeem_invite(token, "tg", "00000") is None
    assert repo.redeem_invite(token, "tg", "67890") is not None


def test_redeem_invite_rejects_when_identity_already_linked(repo, pg_engine):
    user1 = repo.create_user("Existing")
    repo.link_identity(user1, "tg", "111")
    token = repo.create_invite("New", created_by=user1)
    assert repo.redeem_invite(token, "tg", "111") is None
    with pg_engine.connect() as conn:
        used_at = conn.execute(
            text("SELECT used_at FROM auth_invites WHERE token=:token"), {"token": token}
        ).scalar_one()
    assert used_at is None


def test_revoke_removes_identity(repo):
    user_id = repo.create_user("Alice")
    repo.link_identity(user_id, "tg", "12345")
    assert repo.revoke("tg", "12345") is True
    assert repo.is_authorized("tg", "12345") is None


def test_revoke_returns_false_when_not_found(repo):
    assert repo.revoke("tg", "missing") is False


def test_list_identities_returns_dicts(repo):
    user_id = repo.create_user("Alice")
    repo.link_identity(user_id, "tg", "12345")
    rows = repo.list_identities()
    assert len(rows) == 1
    assert rows[0]["channel"] == "tg"
    assert rows[0]["display_name"] == "Alice"


def test_bootstrap_creates_first_user_when_db_empty(repo):
    user_id = repo.bootstrap_admin("Silvio", "tg", "12345678")
    assert repo.is_authorized("tg", "12345678") == user_id


def test_bootstrap_fails_when_db_not_empty(repo):
    repo.create_user("First")
    with pytest.raises(RuntimeError, match="not empty"):
        repo.bootstrap_admin("Silvio", "tg", "12345678")


def test_redeem_invite_concurrent_unbound_token_only_succeeds_once(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    results = []
    errors = []
    barrier = threading.Barrier(2)

    def redeem(channel_id):
        try:
            barrier.wait()
            results.append(repo.redeem_invite(token, "tg", channel_id))
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=redeem, args=("111",))
    t2 = threading.Thread(target=redeem, args=("222",))
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert not errors
    assert len([r for r in results if r is not None]) == 1
```

- [ ] **Step 3: Delete the three old files**

```bash
rm wasp/auth/_connection.py wasp/auth/sqlite_repository.py wasp/auth/postgres_repository.py
```

- [ ] **Step 4: Update `tests/conftest.py` module eviction lists**

In both the setup and teardown `for mod in (...)` blocks, make these changes:

Remove:
```python
"wasp.auth.sqlite_repository",
"wasp.auth.postgres_repository",
"wasp.auth._connection",
```

Add:
```python
"wasp.auth.repository",
"wasp.db",
```

Also update the `_auth_setup._reset_repository()` and `_auth_teardown._reset_repository()` blocks — after each, call `_reset_engine()` from `wasp.db`:

In the setup block (after `_auth_setup._reset_repository()`):
```python
_db_setup = sys.modules.get("wasp.db")
if _db_setup is not None:
    _db_setup._reset_engine()
```

In the teardown block (after `_auth_teardown._reset_repository()`):
```python
_db_teardown = sys.modules.get("wasp.db")
if _db_teardown is not None:
    _db_teardown._reset_engine()
```

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v --ignore=tests/e2e -k "not postgres"
```

Expected: all PASSED, no import errors for removed modules

- [ ] **Step 6: Run postgres tests**

```bash
pytest tests/test_postgres_auth_repository.py -v -m postgres
```

Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add wasp/auth/__init__.py wasp/auth/repository.py wasp/auth/_schema.py \
        tests/test_auth_repository.py tests/test_postgres_auth_repository.py \
        tests/conftest.py
git rm wasp/auth/_connection.py wasp/auth/sqlite_repository.py wasp/auth/postgres_repository.py
git commit -m "refactor(auth): migrate to SQLAlchemy Core, remove sqlite_repository and postgres_repository"
```

---

## Task 6: `wasp/watches/_schema.py` — resource_watches table

**Files:**
- Create: `wasp/watches/__init__.py` (empty for now)
- Create: `wasp/watches/_schema.py`
- Create: `tests/test_watches_repository.py` (partial)

- [ ] **Step 1: Create empty `wasp/watches/__init__.py`**

```python
# populated in Task 8
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_watches_repository.py
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool


@pytest.fixture
def engine(tmp_path):
    e = create_engine(
        f"sqlite:///{tmp_path / 'watches.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    yield e
    e.dispose()


def test_init_schema_creates_resource_watches(engine):
    from wasp.watches._schema import init_schema
    init_schema(engine)
    names = inspect(engine).get_table_names()
    assert "resource_watches" in names


def test_init_schema_is_idempotent(engine):
    from wasp.watches._schema import init_schema
    init_schema(engine)
    init_schema(engine)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_watches_repository.py::test_init_schema_creates_resource_watches \
       tests/test_watches_repository.py::test_init_schema_is_idempotent -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Create `wasp/watches/_schema.py`**

```python
from sqlalchemy import Column, Engine, Integer, MetaData, Table, Text, UniqueConstraint

metadata = MetaData()

resource_watches = Table(
    "resource_watches",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("session_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("notified_at", Text),
    UniqueConstraint("kind", "name"),
)


def init_schema(engine: Engine) -> None:
    metadata.create_all(engine)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_watches_repository.py::test_init_schema_creates_resource_watches \
       tests/test_watches_repository.py::test_init_schema_is_idempotent -v
```

Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add wasp/watches/__init__.py wasp/watches/_schema.py tests/test_watches_repository.py
git commit -m "feat(watches): add resource_watches schema"
```

---

## Task 7: `wasp/watches/repository.py` — WatchRepository CRUD

**Files:**
- Create: `wasp/watches/repository.py`
- Modify: `tests/test_watches_repository.py`

- [ ] **Step 1: Add tests to `tests/test_watches_repository.py`**

Append after the existing schema tests:

```python
@pytest.fixture
def repo(engine):
    from wasp.watches.repository import WatchRepository
    r = WatchRepository(engine=engine)
    r.init_schema()
    return r


def test_register_and_list_pending(repo):
    repo.register("Platform", "my-platform", "tg:agent:12345")
    pending = repo.list_pending()
    assert len(pending) == 1
    assert pending[0] == {"kind": "Platform", "name": "my-platform", "session_id": "tg:agent:12345"}


def test_register_is_idempotent(repo):
    repo.register("Platform", "p1", "tg:agent:1")
    repo.register("Platform", "p1", "tg:agent:1")
    assert len(repo.list_pending()) == 1


def test_complete_removes_from_pending(repo):
    repo.register("Platform", "p1", "tg:agent:1")
    repo.complete("Platform", "p1")
    assert repo.list_pending() == []


def test_fail_removes_from_pending(repo):
    repo.register("Cluster", "c1", "dc:agent:42")
    repo.fail("Cluster", "c1")
    assert repo.list_pending() == []


def test_timeout_removes_from_pending(repo):
    repo.register("Platform", "p2", "tg:agent:2")
    repo.timeout("Platform", "p2")
    assert repo.list_pending() == []


def test_multiple_kinds_are_independent(repo):
    repo.register("Platform", "p1", "tg:agent:1")
    repo.register("Cluster", "c1", "tg:agent:2")
    repo.complete("Platform", "p1")
    pending = repo.list_pending()
    assert len(pending) == 1
    assert pending[0]["kind"] == "Cluster"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_watches_repository.py -v -k "not schema"
```

Expected: `ModuleNotFoundError: No module named 'wasp.watches.repository'`

- [ ] **Step 3: Create `wasp/watches/repository.py`**

```python
from datetime import datetime, timezone

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from wasp.db import get_engine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WatchRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else get_engine()

    def init_schema(self) -> None:
        from wasp.watches._schema import init_schema as _init_schema
        _init_schema(self._engine)

    def register(self, kind: str, name: str, session_id: str) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO resource_watches "
                        "(kind, name, session_id, status, created_at) "
                        "VALUES (:kind, :name, :session_id, 'pending', :created_at)"
                    ),
                    {"kind": kind, "name": name, "session_id": session_id, "created_at": _now()},
                )
        except IntegrityError:
            pass

    def _set_status(self, kind: str, name: str, status: str, notified_at: str | None = None) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE resource_watches SET status=:status, notified_at=:notified_at "
                    "WHERE kind=:kind AND name=:name"
                ),
                {"status": status, "notified_at": notified_at, "kind": kind, "name": name},
            )

    def complete(self, kind: str, name: str) -> None:
        self._set_status(kind, name, "ready", _now())

    def fail(self, kind: str, name: str) -> None:
        self._set_status(kind, name, "failed")

    def timeout(self, kind: str, name: str) -> None:
        self._set_status(kind, name, "timeout")

    def list_pending(self) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT kind, name, session_id FROM resource_watches "
                    "WHERE status='pending'"
                )
            ).fetchall()
        return [{"kind": r[0], "name": r[1], "session_id": r[2]} for r in rows]
```

- [ ] **Step 4: Run all watches repository tests**

```bash
pytest tests/test_watches_repository.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add wasp/watches/repository.py tests/test_watches_repository.py
git commit -m "feat(watches): add WatchRepository with SQLAlchemy Core"
```

---

## Task 8: `wasp/watches/__init__.py` — singleton + restore

**Files:**
- Modify: `wasp/watches/__init__.py`
- Create: `tests/test_watches_restore.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_watches_restore.py
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
def engine(tmp_path):
    e = create_engine(
        f"sqlite:///{tmp_path / 'watches.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    yield e
    e.dispose()


def test_get_repository_returns_singleton(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "w.db"))
    from wasp.db import _reset_engine
    from wasp.watches import _reset_repository, get_repository
    _reset_repository()
    _reset_engine()
    a = get_repository()
    b = get_repository()
    assert a is b
    _reset_repository()
    _reset_engine()


def test_restore_spawns_thread_for_pending_platform(engine, monkeypatch):
    from wasp.watches.repository import WatchRepository
    repo = WatchRepository(engine=engine)
    repo.init_schema()
    repo.register("Platform", "my-platform", "tg:agent:12345")

    spawned = []

    def fake_thread(target=None, daemon=None):
        m = MagicMock()
        spawned.append(target)
        return m

    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock()

    with patch("wasp.watches.get_repository", return_value=repo), \
         patch("wasp.watches.threading.Thread", side_effect=fake_thread), \
         patch("wasp.watcher._select_notifier", return_value=mock_notifier):
        from wasp.watches import restore_pending_watches
        restore_pending_watches()

    assert len(spawned) == 1


def test_restore_skips_watch_with_no_notifier(engine):
    from wasp.watches.repository import WatchRepository
    repo = WatchRepository(engine=engine)
    repo.init_schema()
    repo.register("Platform", "p1", "tg:agent:12345")

    with patch("wasp.watches.get_repository", return_value=repo), \
         patch("wasp.watcher._select_notifier", return_value=None):
        from wasp.watches import restore_pending_watches
        restore_pending_watches()


def test_restore_skips_unknown_kind(engine):
    from wasp.watches.repository import WatchRepository
    repo = WatchRepository(engine=engine)
    repo.init_schema()
    repo.register("Unknown", "x", "tg:agent:1")

    with patch("wasp.watches.get_repository", return_value=repo), \
         patch("wasp.watcher._select_notifier", return_value=MagicMock()):
        from wasp.watches import restore_pending_watches
        restore_pending_watches()


def test_restore_handles_malformed_session_id(engine):
    from wasp.watches.repository import WatchRepository
    repo = WatchRepository(engine=engine)
    repo.init_schema()
    repo.register("Platform", "p1", "bad-session-id")

    with patch("wasp.watches.get_repository", return_value=repo):
        from wasp.watches import restore_pending_watches
        restore_pending_watches()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_watches_restore.py -v
```

Expected: failures related to missing `get_repository`/`restore_pending_watches` in `wasp.watches`

- [ ] **Step 3: Replace `wasp/watches/__init__.py`**

```python
import logging
import threading

log = logging.getLogger(__name__)

_repository = None


def get_repository():
    global _repository
    if _repository is None:
        from wasp.watches.repository import WatchRepository
        r = WatchRepository()
        r.init_schema()
        _repository = r
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None


def restore_pending_watches() -> None:
    from wasp.watcher import _select_notifier, watch_cluster, watch_platform  # lazy — avoids circular import

    for watch in get_repository().list_pending():
        kind = watch["kind"]
        name = watch["name"]
        session_id = watch["session_id"]

        parts = session_id.split(":")
        if len(parts) < 3 or parts[0] not in ("tg", "local", "dc"):
            log.warning("restore: malformed session_id %r for %s/%s — skipping", session_id, kind, name)
            continue

        channel = parts[0]
        chat_id = parts[2]

        notifier = _select_notifier(channel)
        if notifier is None:
            log.warning("restore: no notifier for channel %r — skipping %s/%s", channel, kind, name)
            continue

        if kind == "Platform":
            coro = watch_platform(name, chat_id, notifier)
        elif kind == "Cluster":
            coro = watch_cluster(name, chat_id, notifier)
        else:
            log.warning("restore: unknown kind %r — skipping %s/%s", kind, name, name)
            continue

        log.info("Restoring watch for %s/%s", kind, name)

        def _run(c=coro):
            import asyncio
            asyncio.run(c)

        threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_watches_restore.py -v
```

Expected: all PASSED

- [ ] **Step 5: Update `tests/conftest.py` — add watches modules to eviction list**

In both the setup and teardown `for mod in (...)` blocks, add:

```python
"wasp.watches",
"wasp.watches._schema",
"wasp.watches.repository",
```

Also add watches singleton reset in both setup and teardown — in the setup block (after `_auth_setup._reset_repository()`):

```python
_watches_setup = sys.modules.get("wasp.watches")
if _watches_setup is not None:
    _watches_setup._reset_repository()
```

In the teardown block:
```python
_watches_teardown = sys.modules.get("wasp.watches")
if _watches_teardown is not None:
    _watches_teardown._reset_repository()
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/ -v --ignore=tests/e2e -k "not postgres"
```

Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add wasp/watches/__init__.py tests/test_watches_restore.py tests/conftest.py
git commit -m "feat(watches): add get_repository singleton and restore_pending_watches"
```

---

## Task 9: Update spawners and watch coroutines

Spawners register watches before threading. Watch coroutines call complete/fail/timeout. Provisioners pass session_id to spawn.

**Files:**
- Modify: `wasp/watcher.py`
- Modify: `wasp/resources/platform/provisioner.py`
- Modify: `wasp/resources/cluster/provisioner.py`
- Modify: `tests/test_watcher.py`
- Modify: `tests/test_platform_provisioner.py` (if it exists, check)

- [ ] **Step 1: Check existing watcher tests**

```bash
grep -n "PlatformWatcherSpawner\|ClusterWatcherSpawner\|spawn" tests/test_watcher.py | head -40
```

- [ ] **Step 2: Write failing tests for spawner persistence**

Add to `tests/test_watcher.py`:

```python
def test_platform_spawner_registers_watch_before_threading(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    mock_repo = MagicMock()
    mock_thread_cls = MagicMock()

    with patch("wasp.watcher.threading.Thread", mock_thread_cls), \
         patch("wasp.watcher._select_notifier", return_value=MagicMock()), \
         patch("wasp.watcher.get_watch_repository", return_value=mock_repo):
        spawner = PlatformWatcherSpawner()
        result = spawner.spawn(
            name="p1",
            chat_id="12345",
            channel="tg",
            parent_span_ctx=None,
            session_id="tg:agent:12345",
        )

    assert result is True
    mock_repo.register.assert_called_once_with("Platform", "p1", "tg:agent:12345")
    mock_thread_cls.assert_called_once()


def test_cluster_spawner_registers_watch_before_threading(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import ClusterWatcherSpawner

    mock_repo = MagicMock()
    mock_thread_cls = MagicMock()

    with patch("wasp.watcher.threading.Thread", mock_thread_cls), \
         patch("wasp.watcher._select_notifier", return_value=MagicMock()), \
         patch("wasp.watcher.get_watch_repository", return_value=mock_repo):
        spawner = ClusterWatcherSpawner()
        result = spawner.spawn(
            name="c1",
            chat_id="42",
            channel="dc",
            parent_span_ctx=None,
            session_id="dc:agent:42",
        )

    assert result is True
    mock_repo.register.assert_called_once_with("Cluster", "c1", "dc:agent:42")


def test_spawner_skips_register_when_no_session_id(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    mock_repo = MagicMock()

    with patch("wasp.watcher.threading.Thread", MagicMock()), \
         patch("wasp.watcher._select_notifier", return_value=MagicMock()), \
         patch("wasp.watcher.get_watch_repository", return_value=mock_repo):
        PlatformWatcherSpawner().spawn("p1", "123", "tg", None, session_id=None)

    mock_repo.register.assert_not_called()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_watcher.py -v -k "register"
```

Expected: FAIL — `get_watch_repository` not in `wasp.watcher`

- [ ] **Step 4: Update `wasp/watcher.py` — spawners and watch coroutines**

Add this import alias near the top of `watcher.py` (after existing imports):

```python
from wasp.watches import get_repository as get_watch_repository
```

Update `PlatformWatcherSpawner.spawn` signature and body:

```python
class PlatformWatcherSpawner:
    def spawn(
        self,
        name: str,
        chat_id: str | None,
        channel: str | None,
        parent_span_ctx,
        session_id: str | None = None,
    ) -> bool:
        if not chat_id:
            return False
        chat_id_var.set(chat_id)
        notifier = _select_notifier(channel)
        if notifier is None:
            return False
        if session_id:
            get_watch_repository().register("Platform", name, session_id)

        def _run_watcher():
            asyncio.run(watch_platform(name, chat_id, notifier, parent_span_ctx))

        threading.Thread(target=_run_watcher, daemon=True).start()
        return True
```

Update `ClusterWatcherSpawner.spawn` the same way:

```python
class ClusterWatcherSpawner:
    def spawn(
        self,
        name: str,
        chat_id: str | None,
        channel: str | None,
        parent_span_ctx,
        session_id: str | None = None,
    ) -> bool:
        if not chat_id:
            return False
        chat_id_var.set(chat_id)
        notifier = _select_notifier(channel)
        if notifier is None:
            return False
        if session_id:
            get_watch_repository().register("Cluster", name, session_id)

        def _run_watcher():
            asyncio.run(watch_cluster(name, chat_id, notifier, parent_span_ctx))

        threading.Thread(target=_run_watcher, daemon=True).start()
        return True
```

Update `watch_platform` to call `complete`/`fail` on the repository:

```python
async def watch_platform(
    name: str, chat_id: str, notifier: Notifier, parent_span_ctx=None
) -> None:
    chat_id_var.set(chat_id)
    log.info("Watcher started for %s", name, extra={"platform": name})
    try:
        await _watch_platform_inner(name, chat_id, notifier, parent_span_ctx)
    except Exception:
        log.exception("Watcher failed for %s", name, extra={"platform": name})
        get_watch_repository().fail("Platform", name)
```

In `_watch_platform_inner`, add `complete` and `timeout` calls:

```python
            # In the ready branch (before return):
            get_watch_repository().complete("Platform", name)
            await notifier.send(chat_id, ready_message(name, platform))
            return
            
            # In the timeout branch (before returning from the function):
        get_watch_repository().timeout("Platform", name)
        await notifier.send(
            chat_id,
            f"Provisionamento de '{name}' ainda em andamento após 10 minutos. Verifique mais tarde.",
        )
```

Repeat for `watch_cluster` / `_watch_cluster_inner` using `"Cluster"` instead of `"Platform"`.

- [ ] **Step 5: Update both provisioners to pass `session_id`**

In `wasp/resources/platform/provisioner.py`, change the `spawn` call:

```python
            spawned = self._watcher_spawner.spawn(
                name=name,
                chat_id=chat_id,
                channel=channel,
                parent_span_ctx=span.get_span_context(),
                session_id=getattr(run_context, "session_id", None),
            )
```

In `wasp/resources/cluster/provisioner.py`, the same change:

```python
            spawned = self._watcher_spawner.spawn(
                name=name,
                chat_id=chat_id,
                channel=channel,
                parent_span_ctx=span.get_span_context(),
                session_id=getattr(run_context, "session_id", None),
            )
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_watcher.py tests/test_provision.py \
       tests/test_cluster_provisioner.py -v
```

Expected: all PASSED (fix any test that now asserts `spawn` was called without `session_id` by adding `session_id=None`)

- [ ] **Step 7: Commit**

```bash
git add wasp/watcher.py \
        wasp/resources/platform/provisioner.py \
        wasp/resources/cluster/provisioner.py \
        tests/test_watcher.py
git commit -m "feat(watcher): persist watches on spawn; complete/fail/timeout on exit"
```

---

## Task 10: Update `main.py` — call `restore_pending_watches`

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write a failing test**

Look at existing `tests/test_main.py` to understand the test structure, then add:

```python
def test_create_app_calls_restore_pending_watches(monkeypatch):
    from unittest.mock import MagicMock, patch
    with patch("wasp.watches.restore_pending_watches") as mock_restore:
        import main  # noqa: F401
        # Trigger the module-level create_app call by importing main
        # If main is already imported, the call already happened
        mock_restore.assert_called_once()
```

Note: the test structure may need adjustment based on how `test_main.py` currently mocks dependencies. Read the file first and match the existing pattern.

- [ ] **Step 2: Run to verify the test fails**

```bash
pytest tests/test_main.py -v -k "restore"
```

- [ ] **Step 3: Update `main.py`**

Add after `app, agent_os = create_app()`:

```python
from wasp.watches import restore_pending_watches  # noqa: E402

restore_pending_watches()
```

- [ ] **Step 4: Run all main tests**

```bash
pytest tests/test_main.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat(main): restore pending watches after app startup"
```

---

## Task 11: Full validation

- [ ] **Step 1: Format**

```bash
make format
```

- [ ] **Step 2: Full test suite with coverage**

```bash
make test
```

Expected: all PASSED, coverage 100%

- [ ] **Step 3: E2E**

```bash
make e2e-with-debug
```

Expected: PASSED

- [ ] **Step 4: If any coverage gaps exist**

Check `pytest --cov --cov-report=term-missing` output. Add any missing test for uncovered lines. Common gaps:
- `wasp/watches/__init__.py` logging paths (malformed session_id, missing notifier, unknown kind)
- `wasp/db/__init__.py` `_build_engine` Postgres branch (covered by `test_db_engine.py`)

- [ ] **Step 5: Final commit if needed**

```bash
git add -p
git commit -m "test: fill coverage gaps in watches and db modules"
```
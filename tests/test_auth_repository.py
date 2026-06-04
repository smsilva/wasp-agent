import sqlite3
from datetime import datetime, timedelta

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
    from wasp.db import _reset_engine
    _reset_engine()
    from wasp.auth.repository import AuthRepository
    repo = AuthRepository()
    repo.init_schema()
    assert repo.has_any_user() is False
    user_id = repo.create_user("Alice")
    repo.link_identity(user_id, "tg", "1")
    assert repo.is_authorized("tg", "1") == user_id
    _reset_engine()

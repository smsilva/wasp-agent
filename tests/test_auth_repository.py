import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from wasp.auth.sqlite_repository import SqliteAuthRepository


@pytest.fixture
def repo(tmp_path):
    return SqliteAuthRepository(str(tmp_path / "agent.db"))


def _table_names(db_file):
    con = sqlite3.connect(db_file)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        con.close()


def test_init_schema_creates_three_tables(repo):
    repo.init_schema()
    names = _table_names(repo._db_file)
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names


def test_init_schema_is_idempotent(repo):
    repo.init_schema()
    repo.init_schema()
    names = _table_names(repo._db_file)
    assert "auth_users" in names


def test_is_authorized_returns_none_for_unknown(repo):
    assert repo.is_authorized("tg", "12345") is None


def test_create_user_and_link_identity(repo):
    user_id = repo.create_user("Alice")
    assert isinstance(user_id, str)
    assert len(user_id) == 32
    repo.link_identity(user_id, "tg", "12345")
    assert repo.is_authorized("tg", "12345") == user_id


def test_create_invite_returns_urlsafe_token(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    assert isinstance(token, str)
    assert len(token) >= 40


def test_redeem_invite_creates_identity_and_returns_user(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    result = repo.redeem_invite(token, "tg", "67890")
    assert result is not None
    user_id, display_name = result
    assert display_name == "Bob"
    assert repo.is_authorized("tg", "67890") == user_id


def test_redeem_invite_returns_none_for_unknown_token(repo):
    repo.init_schema()
    assert repo.redeem_invite("nonexistent", "tg", "1") is None


def test_redeem_invite_returns_none_when_expired(repo):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    con = sqlite3.connect(repo._db_file)
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
    token = repo.create_invite(
        "Bob", created_by=admin, channel="tg", channel_id="67890"
    )
    assert repo.redeem_invite(token, "discord", "67890") is None
    assert repo.redeem_invite(token, "tg", "00000") is None
    assert repo.redeem_invite(token, "tg", "67890") is not None


def test_redeem_invite_rejects_when_identity_already_linked(repo):
    user1 = repo.create_user("Existing")
    repo.link_identity(user1, "tg", "111")
    token = repo.create_invite("New", created_by=user1)
    assert repo.redeem_invite(token, "tg", "111") is None
    con = sqlite3.connect(repo._db_file)
    try:
        used_at = con.execute(
            "SELECT used_at FROM auth_invites WHERE token=?", (token,)
        ).fetchone()[0]
    finally:
        con.close()
    assert used_at is None


def test_revoke_removes_identity_keeps_user(repo):
    user_id = repo.create_user("Alice")
    repo.link_identity(user_id, "tg", "12345")
    assert repo.revoke("tg", "12345") is True
    assert repo.is_authorized("tg", "12345") is None


def test_revoke_returns_false_when_not_found(repo):
    repo.init_schema()
    assert repo.revoke("tg", "missing") is False


def test_list_identities_returns_dicts(repo):
    user_id = repo.create_user("Alice")
    repo.link_identity(user_id, "tg", "12345")
    rows = repo.list_identities()
    assert len(rows) == 1
    assert rows[0]["channel"] == "tg"
    assert rows[0]["channel_id"] == "12345"
    assert rows[0]["user_id"] == user_id
    assert rows[0]["display_name"] == "Alice"
    assert "linked_at" in rows[0]


def test_has_any_user_false_then_true(repo):
    assert repo.has_any_user() is False
    repo.create_user("Alice")
    assert repo.has_any_user() is True


def test_bootstrap_creates_first_user_when_db_empty(repo):
    user_id = repo.bootstrap_admin("Silvio", "tg", "12345678")
    assert user_id
    assert repo.is_authorized("tg", "12345678") == user_id


def test_bootstrap_fails_when_db_not_empty(repo):
    repo.create_user("First")
    with pytest.raises(RuntimeError, match="not empty"):
        repo.bootstrap_admin("Silvio", "tg", "12345678")


def test_create_user_persists_display_name_in_sqlite(repo):
    user_id = repo.create_user("Alice")
    con = sqlite3.connect(repo._db_file)
    try:
        row = con.execute(
            "SELECT display_name FROM auth_users WHERE user_id=?", (user_id,)
        ).fetchone()
        assert row is not None
        assert row[0] == "Alice"
    finally:
        con.close()


def test_create_invite_default_ttl_is_one_hour(repo, monkeypatch):
    monkeypatch.delenv("WASP_AGENT_INVITE_TTL_HOURS", raising=False)
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    con = sqlite3.connect(repo._db_file)
    try:
        row = con.execute(
            "SELECT created_at, expires_at FROM auth_invites WHERE token=?",
            (token,),
        ).fetchone()
    finally:
        con.close()
    created = datetime.fromisoformat(row[0])
    expires = datetime.fromisoformat(row[1])
    assert expires - created == timedelta(hours=1)


def test_init_schema_no_args_uses_env_var(tmp_path, monkeypatch):
    target = str(tmp_path / "init_env.db")
    monkeypatch.setenv("WASP_AGENT_DB_FILE", target)
    SqliteAuthRepository().init_schema()
    con = sqlite3.connect(target)
    try:
        names = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        con.close()
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names


def test_create_invite_uses_env_ttl(repo, monkeypatch):
    monkeypatch.setenv("WASP_AGENT_INVITE_TTL_HOURS", "5")
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    con = sqlite3.connect(repo._db_file)
    try:
        row = con.execute(
            "SELECT created_at, expires_at FROM auth_invites WHERE token=?",
            (token,),
        ).fetchone()
    finally:
        con.close()
    created = datetime.fromisoformat(row[0])
    expires = datetime.fromisoformat(row[1])
    assert expires - created == timedelta(hours=5)


def test_db_file_defaults_to_env_var(tmp_path, monkeypatch):
    target = str(tmp_path / "from_env.db")
    monkeypatch.setenv("WASP_AGENT_DB_FILE", target)
    repo = SqliteAuthRepository()
    assert repo.has_any_user() is False
    user_id = repo.create_user("Alice")
    repo.link_identity(user_id, "tg", "1")
    assert repo.is_authorized("tg", "1") == user_id


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
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    successes = [r for r in results if r is not None]
    assert len(successes) == 1


def test_get_repository_returns_singleton(monkeypatch, tmp_path):
    monkeypatch.setenv("WASP_AGENT_DB_FILE", str(tmp_path / "singleton.db"))
    from wasp import auth

    auth._reset_repository()
    a = auth.get_repository()
    b = auth.get_repository()
    assert a is b
    auth._reset_repository()


def test_get_repository_unsupported_backend_raises(monkeypatch):
    monkeypatch.setenv("WASP_AGENT_DB_BACKEND", "postgres")
    from wasp import auth

    auth._reset_repository()
    with pytest.raises(ValueError, match="unsupported backend"):
        auth.get_repository()
    auth._reset_repository()


def test_shim_resolves_env_per_call(monkeypatch, tmp_path):
    target = str(tmp_path / "shim_env.db")
    monkeypatch.setenv("WASP_AGENT_DB_FILE", target)
    from wasp import auth

    user_id = auth.create_user("Alice")
    assert auth.is_authorized("tg", "x") is None
    auth.link_identity(user_id, "tg", "x")
    assert auth.is_authorized("tg", "x") == user_id


def test_shim_covers_remaining_functions(monkeypatch, tmp_path):
    """Covers shim wrappers for init_db, create_invite, redeem_invite, revoke,
    list_identities, has_any_user, and bootstrap_admin."""
    target = str(tmp_path / "shim_full.db")
    monkeypatch.setenv("WASP_AGENT_DB_FILE", target)
    from wasp import auth

    auth.init_db()
    assert auth.has_any_user() is False
    admin_id = auth.bootstrap_admin("Admin", "tg", "9999")
    assert auth.has_any_user() is True
    token = auth.create_invite("Bob", created_by=admin_id)
    result = auth.redeem_invite(token, "tg", "1234")
    assert result is not None
    rows = auth.list_identities()
    assert any(r["channel_id"] == "9999" for r in rows)
    assert auth.revoke("tg", "1234") is True

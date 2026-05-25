import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from wasp import auth


@pytest.fixture
def db_file(tmp_path):
    return str(tmp_path / "agent.db")


def _table_names(db_file):
    con = sqlite3.connect(db_file)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        con.close()


def test_init_db_creates_three_tables(db_file):
    auth.init_db(db_file)
    names = _table_names(db_file)
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names


def test_init_db_is_idempotent(db_file):
    auth.init_db(db_file)
    auth.init_db(db_file)
    names = _table_names(db_file)
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names


def test_is_authorized_returns_none_for_unknown(db_file):
    assert auth.is_authorized("tg", "12345", db_file=db_file) is None


def test_create_user_returns_uuid_and_persists(db_file):
    user_id = auth.create_user("Alice", db_file=db_file)
    assert isinstance(user_id, str)
    assert len(user_id) == 32  # uuid4().hex
    con = sqlite3.connect(db_file)
    try:
        row = con.execute(
            "SELECT display_name FROM auth_users WHERE user_id=?", (user_id,)
        ).fetchone()
        assert row is not None
        assert row[0] == "Alice"
    finally:
        con.close()


def test_link_identity_allows_is_authorized(db_file):
    user_id = auth.create_user("Alice", db_file=db_file)
    auth.link_identity(user_id, "tg", "12345", db_file=db_file)
    assert auth.is_authorized("tg", "12345", db_file=db_file) == user_id


def test_create_invite_returns_urlsafe_token(db_file):
    user_id = auth.create_user("Alice", db_file=db_file)
    token = auth.create_invite(display_name="Bob", created_by=user_id, db_file=db_file)
    assert isinstance(token, str)
    assert len(token) >= 40


def test_create_invite_persists_with_expires_at_from_default_ttl(db_file, monkeypatch):
    monkeypatch.delenv("WASP_AGENT_INVITE_TTL_HOURS", raising=False)
    user_id = auth.create_user("Alice", db_file=db_file)
    token = auth.create_invite(display_name="Bob", created_by=user_id, db_file=db_file)
    con = sqlite3.connect(db_file)
    try:
        row = con.execute(
            "SELECT created_at, expires_at FROM auth_invites WHERE token=?",
            (token,),
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    created = datetime.fromisoformat(row[0])
    expires = datetime.fromisoformat(row[1])
    # Default TTL is 1 hour.
    delta = expires - created
    assert delta == timedelta(hours=1)


def test_create_invite_uses_env_ttl(db_file, monkeypatch):
    monkeypatch.setenv("WASP_AGENT_INVITE_TTL_HOURS", "5")
    user_id = auth.create_user("Alice", db_file=db_file)
    token = auth.create_invite(display_name="Bob", created_by=user_id, db_file=db_file)
    con = sqlite3.connect(db_file)
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


def test_redeem_invite_creates_identity_and_returns_user(db_file):
    admin = auth.create_user("Admin", db_file=db_file)
    token = auth.create_invite(display_name="Bob", created_by=admin, db_file=db_file)
    result = auth.redeem_invite(token, "tg", "67890", db_file=db_file)
    assert result is not None
    user_id, display_name = result
    assert display_name == "Bob"
    assert auth.is_authorized("tg", "67890", db_file=db_file) == user_id
    con = sqlite3.connect(db_file)
    try:
        used_at = con.execute(
            "SELECT used_at FROM auth_invites WHERE token=?", (token,)
        ).fetchone()[0]
    finally:
        con.close()
    assert used_at is not None


def test_redeem_invite_returns_none_for_unknown_token(db_file):
    auth.init_db(db_file)
    assert auth.redeem_invite("nonexistent", "tg", "1", db_file=db_file) is None


def test_redeem_invite_returns_none_when_expired(db_file):
    admin = auth.create_user("Admin", db_file=db_file)
    token = auth.create_invite(display_name="Bob", created_by=admin, db_file=db_file)
    # Backdate expiration to past.
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    con = sqlite3.connect(db_file)
    try:
        con.execute("UPDATE auth_invites SET expires_at=? WHERE token=?", (past, token))
        con.commit()
    finally:
        con.close()
    assert auth.redeem_invite(token, "tg", "67890", db_file=db_file) is None


def test_redeem_invite_returns_none_when_already_consumed(db_file):
    admin = auth.create_user("Admin", db_file=db_file)
    token = auth.create_invite(display_name="Bob", created_by=admin, db_file=db_file)
    first = auth.redeem_invite(token, "tg", "67890", db_file=db_file)
    assert first is not None
    second = auth.redeem_invite(token, "tg", "11111", db_file=db_file)
    assert second is None


def test_redeem_invite_rejects_channel_mismatch(db_file):
    admin = auth.create_user("Admin", db_file=db_file)
    token = auth.create_invite(
        display_name="Bob",
        created_by=admin,
        channel="tg",
        channel_id="67890",
        db_file=db_file,
    )
    # Different channel should be rejected.
    assert auth.redeem_invite(token, "discord", "67890", db_file=db_file) is None
    # Different channel_id should be rejected.
    assert auth.redeem_invite(token, "tg", "00000", db_file=db_file) is None
    # Matching pair should succeed.
    result = auth.redeem_invite(token, "tg", "67890", db_file=db_file)
    assert result is not None


def test_revoke_removes_identity_keeps_user(db_file):
    user_id = auth.create_user("Alice", db_file=db_file)
    auth.link_identity(user_id, "tg", "12345", db_file=db_file)
    assert auth.revoke("tg", "12345", db_file=db_file) is True
    assert auth.is_authorized("tg", "12345", db_file=db_file) is None
    # User still exists.
    con = sqlite3.connect(db_file)
    try:
        row = con.execute(
            "SELECT user_id FROM auth_users WHERE user_id=?", (user_id,)
        ).fetchone()
    finally:
        con.close()
    assert row is not None


def test_revoke_returns_false_when_not_found(db_file):
    auth.init_db(db_file)
    assert auth.revoke("tg", "missing", db_file=db_file) is False


def test_list_identities_returns_dicts(db_file):
    user_id = auth.create_user("Alice", db_file=db_file)
    auth.link_identity(user_id, "tg", "12345", db_file=db_file)
    rows = auth.list_identities(db_file=db_file)
    assert len(rows) == 1
    row = rows[0]
    assert row["channel"] == "tg"
    assert row["channel_id"] == "12345"
    assert row["user_id"] == user_id
    assert row["display_name"] == "Alice"
    assert "linked_at" in row


def test_has_any_user_false_then_true(db_file):
    assert auth.has_any_user(db_file=db_file) is False
    auth.create_user("Alice", db_file=db_file)
    assert auth.has_any_user(db_file=db_file) is True


def test_db_file_defaults_to_env_var(tmp_path, monkeypatch):
    target = str(tmp_path / "from_env.db")
    monkeypatch.setenv("WASP_AGENT_DB_FILE", target)
    assert auth.has_any_user() is False
    user_id = auth.create_user("Alice")
    assert auth.is_authorized("tg", "1") is None
    auth.link_identity(user_id, "tg", "1")
    assert auth.is_authorized("tg", "1") == user_id


def test_init_db_without_args_uses_env_var(tmp_path, monkeypatch):
    target = str(tmp_path / "init_env.db")
    monkeypatch.setenv("WASP_AGENT_DB_FILE", target)
    auth.init_db()
    names = _table_names(target)
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names


def test_bootstrap_creates_first_user_when_db_empty(db_file):
    user_id = auth.bootstrap_admin("Silvio", "tg", "12345678", db_file=db_file)
    assert user_id
    assert auth.is_authorized("tg", "12345678", db_file=db_file) == user_id


def test_bootstrap_fails_when_db_not_empty(db_file):
    auth.create_user("First", db_file=db_file)
    with pytest.raises(RuntimeError, match="not empty"):
        auth.bootstrap_admin("Silvio", "tg", "12345678", db_file=db_file)


def test_redeem_invite_concurrent_unbound_token_only_succeeds_once(db_file):
    """Two concurrent redemptions of the same unbound invite must not both succeed.

    Without BEGIN IMMEDIATE, both threads can read used_at=NULL and then both
    link a different channel_id (no PK conflict) — double-claiming one invite.
    """
    admin = auth.create_user("Admin", db_file=db_file)
    token = auth.create_invite(display_name="Bob", created_by=admin, db_file=db_file)

    results = []
    barrier = threading.Barrier(2)
    errors = []

    def redeem(channel_id):
        try:
            barrier.wait()
            result = auth.redeem_invite(token, "tg", channel_id, db_file=db_file)
            results.append(result)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=redeem, args=("111",))
    t2 = threading.Thread(target=redeem, args=("222",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Unexpected errors: {errors}"
    successes = [r for r in results if r is not None]
    assert len(successes) == 1, (
        f"Expected exactly 1 successful redemption, got {len(successes)}: {results}"
    )


def test_redeem_invite_rejects_when_identity_already_linked(db_file):
    # Pre-existing identity for (tg, "111")
    user1 = auth.create_user("Existing", db_file=db_file)
    auth.link_identity(user1, "tg", "111", db_file=db_file)
    # New invite, attempting to bind same (tg, "111")
    token = auth.create_invite("New", created_by=user1, db_file=db_file)
    assert auth.redeem_invite(token, "tg", "111", db_file=db_file) is None
    # Invite remains unconsumed (admin can revoke existing identity and retry).
    con = sqlite3.connect(db_file)
    try:
        used_at = con.execute(
            "SELECT used_at FROM auth_invites WHERE token=?", (token,)
        ).fetchone()[0]
    finally:
        con.close()
    assert used_at is None

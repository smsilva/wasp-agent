import threading
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url(driver=None)


@pytest.fixture
def repo(pg_url):
    from wasp.auth.postgres_repository import PostgresAuthRepository

    r = PostgresAuthRepository(pg_url)
    r.init_schema()
    with psycopg.connect(pg_url) as con:
        con.execute("TRUNCATE auth_invites, auth_identities, auth_users CASCADE")
        con.commit()
    return r


def _table_names(pg_url):
    with psycopg.connect(pg_url) as con:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public'"
        ).fetchall()
    return {row[0] for row in rows}


def test_init_schema_creates_three_tables(repo, pg_url):
    names = _table_names(pg_url)
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names


def test_init_schema_is_idempotent(repo, pg_url):
    repo.init_schema()
    names = _table_names(pg_url)
    assert "auth_users" in names


def test_is_authorized_returns_none_for_unknown(repo):
    assert repo.is_authorized("tg", "12345") is None


def test_create_user_and_link_identity(repo):
    user_id = repo.create_user("Alice")
    assert isinstance(user_id, str)
    assert len(user_id) == 32
    repo.link_identity(user_id, "tg", "12345")
    assert repo.is_authorized("tg", "12345") == user_id


def test_has_any_user_false_then_true(repo):
    assert repo.has_any_user() is False
    repo.create_user("Alice")
    assert repo.has_any_user() is True


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
    assert repo.redeem_invite("nonexistent", "tg", "1") is None


def test_redeem_invite_returns_none_when_expired(repo, pg_url):
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with psycopg.connect(pg_url) as con:
        con.execute(
            "UPDATE auth_invites SET expires_at=%s WHERE token=%s", (past, token)
        )
        con.commit()
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


def test_redeem_invite_rejects_when_identity_already_linked(repo, pg_url):
    user1 = repo.create_user("Existing")
    repo.link_identity(user1, "tg", "111")
    token = repo.create_invite("New", created_by=user1)
    assert repo.redeem_invite(token, "tg", "111") is None
    with psycopg.connect(pg_url) as con:
        used_at = con.execute(
            "SELECT used_at FROM auth_invites WHERE token=%s", (token,)
        ).fetchone()[0]
    assert used_at is None


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
    assert rows[0]["channel"] == "tg"
    assert rows[0]["channel_id"] == "12345"
    assert rows[0]["user_id"] == user_id
    assert rows[0]["display_name"] == "Alice"
    assert "linked_at" in rows[0]


def test_bootstrap_creates_first_user_when_db_empty(repo):
    user_id = repo.bootstrap_admin("Silvio", "tg", "12345678")
    assert user_id
    assert repo.is_authorized("tg", "12345678") == user_id


def test_bootstrap_fails_when_db_not_empty(repo):
    repo.create_user("First")
    with pytest.raises(RuntimeError, match="not empty"):
        repo.bootstrap_admin("Silvio", "tg", "12345678")


def test_create_invite_default_ttl_is_one_hour(repo, pg_url, monkeypatch):
    monkeypatch.delenv("AGENT_INVITE_TTL_HOURS", raising=False)
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    with psycopg.connect(pg_url) as con:
        row = con.execute(
            "SELECT created_at, expires_at FROM auth_invites WHERE token=%s",
            (token,),
        ).fetchone()
    created = datetime.fromisoformat(row[0])
    expires = datetime.fromisoformat(row[1])
    assert expires - created == timedelta(hours=1)


def test_create_invite_uses_env_ttl(repo, pg_url, monkeypatch):
    monkeypatch.setenv("AGENT_INVITE_TTL_HOURS", "5")
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    with psycopg.connect(pg_url) as con:
        row = con.execute(
            "SELECT created_at, expires_at FROM auth_invites WHERE token=%s",
            (token,),
        ).fetchone()
    created = datetime.fromisoformat(row[0])
    expires = datetime.fromisoformat(row[1])
    assert expires - created == timedelta(hours=5)


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


def test_dsn_defaults_to_env_var(pg_url, monkeypatch):
    from wasp.auth.postgres_repository import PostgresAuthRepository

    monkeypatch.setenv("DATABASE_URL", pg_url)
    repo = PostgresAuthRepository()
    assert repo.has_any_user() in (True, False)

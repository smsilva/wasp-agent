import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url(driver="psycopg")


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
    token = repo.create_invite(
        "Bob", created_by=admin, channel="tg", channel_id="67890"
    )
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
            text("SELECT used_at FROM auth_invites WHERE token=:token"),
            {"token": token},
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
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not errors
    assert len([r for r in results if r is not None]) == 1

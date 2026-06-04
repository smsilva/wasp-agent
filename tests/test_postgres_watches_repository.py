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
    from wasp.watches.repository import WatchRepository

    r = WatchRepository(engine=pg_engine)
    r.init_schema()
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE resource_watches"))
    return r


def test_register_and_list_pending(repo):
    repo.register("Platform", "my-platform", "tg:agent:12345")
    pending = repo.list_pending()
    assert pending == [
        {"kind": "Platform", "name": "my-platform", "session_id": "tg:agent:12345"}
    ]


def test_register_is_idempotent(repo):
    repo.register("Platform", "p1", "tg:agent:1")
    repo.register("Platform", "p1", "tg:agent:1")
    assert len(repo.list_pending()) == 1


def test_register_after_terminal_state_resets_to_pending(repo):
    repo.register("Platform", "p1", "tg:agent:1")
    repo.complete("Platform", "p1")
    assert repo.list_pending() == []

    repo.register("Platform", "p1", "tg:agent:2")
    pending = repo.list_pending()
    assert pending == [{"kind": "Platform", "name": "p1", "session_id": "tg:agent:2"}]

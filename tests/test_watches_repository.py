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
    assert pending[0] == {
        "kind": "Platform",
        "name": "my-platform",
        "session_id": "tg:agent:12345",
    }


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


def test_register_after_terminal_state_resets_to_pending(repo):
    repo.register("Platform", "p1", "tg:agent:1")
    repo.complete("Platform", "p1")
    assert repo.list_pending() == []

    repo.register("Platform", "p1", "tg:agent:2")
    pending = repo.list_pending()
    assert len(pending) == 1
    assert pending[0] == {
        "kind": "Platform",
        "name": "p1",
        "session_id": "tg:agent:2",
    }


def test_multiple_kinds_are_independent(repo):
    repo.register("Platform", "p1", "tg:agent:1")
    repo.register("Cluster", "c1", "tg:agent:2")
    repo.complete("Platform", "p1")
    pending = repo.list_pending()
    assert len(pending) == 1
    assert pending[0]["kind"] == "Cluster"

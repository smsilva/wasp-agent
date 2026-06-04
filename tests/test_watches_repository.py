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

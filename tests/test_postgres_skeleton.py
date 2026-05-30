import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.postgres


def test_postgres_container_select_one():
    with PostgresContainer("postgres:16-alpine") as pg:
        with psycopg.connect(pg.get_connection_url(driver=None)) as conn:
            row = conn.execute("SELECT 1").fetchone()
    assert row == (1,)

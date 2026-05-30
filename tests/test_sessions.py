import pytest


def test_build_session_db_defaults_to_sqlite(mock_agno, monkeypatch):
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_FILE", raising=False)

    from wasp.sessions import build_session_db

    build_session_db()

    mock_agno["agno.db.sqlite.sqlite"].SqliteDb.assert_called_once_with(
        db_file="agent.db", session_table="agent_sessions"
    )


def test_build_session_db_sqlite_reads_database_file(mock_agno, monkeypatch):
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    monkeypatch.setenv("DATABASE_FILE", "/tmp/custom.db")

    from wasp.sessions import build_session_db

    build_session_db()

    mock_agno["agno.db.sqlite.sqlite"].SqliteDb.assert_called_once_with(
        db_file="/tmp/custom.db", session_table="agent_sessions"
    )


def test_build_session_db_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "mongo")

    from wasp.sessions import build_session_db

    with pytest.raises(ValueError, match="unsupported backend: mongo"):
        build_session_db()


def test_build_session_db_postgres_raises_not_implemented(mock_agno, monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "postgres")

    from wasp.sessions import build_session_db

    with pytest.raises(NotImplementedError, match="Postgres backend for agno sessions not yet wired"):
        build_session_db()

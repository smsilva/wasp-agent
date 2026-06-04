import pytest


def test_get_engine_sqlite_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "test.db"))
    from wasp.db import _reset_engine, get_engine
    _reset_engine()
    engine = get_engine()
    assert "sqlite" in str(engine.url)
    assert "test.db" in str(engine.url)
    _reset_engine()


def test_get_engine_returns_singleton(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "s.db"))
    from wasp.db import _reset_engine, get_engine
    _reset_engine()
    a = get_engine()
    b = get_engine()
    assert a is b
    _reset_engine()


def test_get_engine_postgres_uses_database_url(monkeypatch):
    """Verify postgres backend uses DATABASE_URL (without actually importing psycopg2)."""
    monkeypatch.setenv("DATABASE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    from wasp.db import _reset_engine, _build_engine
    _reset_engine()
    # Mock create_engine to avoid driver import.
    import unittest.mock
    with unittest.mock.patch("wasp.db.create_engine") as mock_create:
        mock_create.return_value = unittest.mock.MagicMock()
        _build_engine()
        mock_create.assert_called_once_with("postgresql+psycopg://u:p@localhost/db")
    _reset_engine()


def test_get_engine_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "mongo")
    from wasp.db import _reset_engine, get_engine
    _reset_engine()
    with pytest.raises(ValueError, match="unsupported"):
        get_engine()
    _reset_engine()
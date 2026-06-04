import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def _reset_engine() -> None:
    global _engine
    _engine = None


def _build_engine() -> Engine:
    backend = os.getenv("DATABASE_BACKEND", "sqlite")
    if backend == "sqlite":
        db_file = os.getenv("DATABASE_FILE", "agent.db")
        return create_engine(
            f"sqlite:///{db_file}",
            poolclass=NullPool,
            connect_args={"check_same_thread": False},
        )
    if backend == "postgres":
        url = os.environ["DATABASE_URL"]
        return create_engine(url)
    raise ValueError(f"unsupported DATABASE_BACKEND: {backend}")

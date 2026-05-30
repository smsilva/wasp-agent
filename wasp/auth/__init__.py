import os

from wasp.auth.protocol import AuthRepository as AuthRepository
from wasp.auth.sqlite_repository import SqliteAuthRepository as SqliteAuthRepository

__all__ = ["AuthRepository", "SqliteAuthRepository", "get_repository"]

_repository: AuthRepository | None = None


def get_repository() -> AuthRepository:
    global _repository
    if _repository is None:
        backend = os.getenv("DATABASE_BACKEND", "sqlite")
        if backend == "sqlite":
            _repository = SqliteAuthRepository()
        elif backend == "postgres":
            from wasp.auth.postgres_repository import PostgresAuthRepository

            _repository = PostgresAuthRepository()
        else:
            raise ValueError(f"unsupported backend: {backend}")
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None

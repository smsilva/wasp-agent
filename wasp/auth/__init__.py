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
            try:
                from wasp.auth.postgres_repository import PostgresAuthRepository
            except ImportError as e:
                raise NotImplementedError(
                    "Postgres backend not yet implemented "
                    "(wasp/auth/postgres_repository.py missing). "
                    "See docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
                ) from e
            _repository = PostgresAuthRepository()  # pragma: no cover
        else:
            raise ValueError(f"unsupported backend: {backend}")
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None

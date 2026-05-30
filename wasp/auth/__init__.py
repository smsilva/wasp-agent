import os

from wasp.auth.protocol import AuthRepository as AuthRepository
from wasp.auth.sqlite_repository import SqliteAuthRepository as SqliteAuthRepository

__all__ = ["AuthRepository", "SqliteAuthRepository", "get_repository"]

_repository: AuthRepository | None = None


def get_repository() -> AuthRepository:
    global _repository
    if _repository is None:
        backend = os.getenv("WASP_AGENT_DB_BACKEND", "sqlite")
        if backend == "sqlite":
            _repository = SqliteAuthRepository()
        else:
            raise ValueError(f"unsupported backend: {backend}")
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None

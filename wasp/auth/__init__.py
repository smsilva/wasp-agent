import os

from wasp.auth.protocol import AuthRepository as AuthRepository
from wasp.auth.sqlite_repository import SqliteAuthRepository as SqliteAuthRepository

__all__ = [
    "AuthRepository",
    "SqliteAuthRepository",
    "get_repository",
    "init_db",
    "is_authorized",
    "create_user",
    "link_identity",
    "create_invite",
    "redeem_invite",
    "revoke",
    "list_identities",
    "has_any_user",
    "bootstrap_admin",
]

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


def _repo(db_file: str | None) -> AuthRepository:
    # Build per call so WASP_AGENT_DB_FILE env changes (tests, multi-tenant CLIs)
    # are honored. Long-lived processes should use get_repository() directly.
    return SqliteAuthRepository(db_file)


def init_db(db_file: str | None = None) -> None:
    _repo(db_file).init_schema()


def is_authorized(
    channel: str, channel_id: str, db_file: str | None = None
) -> str | None:
    return _repo(db_file).is_authorized(channel, channel_id)


def create_user(display_name: str, db_file: str | None = None) -> str:
    return _repo(db_file).create_user(display_name)


def link_identity(
    user_id: str, channel: str, channel_id: str, db_file: str | None = None
) -> None:
    return _repo(db_file).link_identity(user_id, channel, channel_id)


def create_invite(
    display_name: str,
    created_by: str,
    channel: str | None = None,
    channel_id: str | None = None,
    db_file: str | None = None,
) -> str:
    return _repo(db_file).create_invite(display_name, created_by, channel, channel_id)


def redeem_invite(
    token: str, channel: str, channel_id: str, db_file: str | None = None
) -> tuple[str, str] | None:
    return _repo(db_file).redeem_invite(token, channel, channel_id)


def revoke(channel: str, channel_id: str, db_file: str | None = None) -> bool:
    return _repo(db_file).revoke(channel, channel_id)


def list_identities(db_file: str | None = None) -> list[dict]:
    return _repo(db_file).list_identities()


def has_any_user(db_file: str | None = None) -> bool:
    return _repo(db_file).has_any_user()


def bootstrap_admin(
    display_name: str, channel: str, channel_id: str, db_file: str | None = None
) -> str:
    return _repo(db_file).bootstrap_admin(display_name, channel, channel_id)

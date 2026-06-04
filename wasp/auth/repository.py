import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, text

from wasp.db import get_engine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuthRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else get_engine()

    def init_schema(self) -> None:
        from wasp.auth._schema import init_schema as _init_schema

        _init_schema(self._engine)

    def is_authorized(self, channel: str, channel_id: str) -> str | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT user_id FROM auth_identities "
                    "WHERE channel=:channel AND channel_id=:channel_id"
                ),
                {"channel": channel, "channel_id": channel_id},
            ).one_or_none()
            return row[0] if row else None

    def create_user(self, display_name: str) -> str:
        user_id = uuid.uuid4().hex
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO auth_users (user_id, display_name, created_at) "
                    "VALUES (:user_id, :display_name, :created_at)"
                ),
                {
                    "user_id": user_id,
                    "display_name": display_name,
                    "created_at": _now(),
                },
            )
        return user_id

    def link_identity(self, user_id: str, channel: str, channel_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                    "VALUES (:channel, :channel_id, :user_id, :linked_at)"
                ),
                {
                    "channel": channel,
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "linked_at": _now(),
                },
            )

    def has_any_user(self) -> bool:
        with self._engine.connect() as conn:
            return (
                conn.execute(text("SELECT 1 FROM auth_users LIMIT 1")).one_or_none()
                is not None
            )

    def create_invite(
        self,
        display_name: str,
        created_by: str,
        channel: str | None = None,
        channel_id: str | None = None,
    ) -> str:
        ttl_hours = int(os.getenv("AGENT_INVITE_TTL_HOURS", "1"))
        user_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO auth_users (user_id, display_name, created_at) "
                    "VALUES (:user_id, :display_name, :created_at)"
                ),
                {
                    "user_id": user_id,
                    "display_name": display_name,
                    "created_at": created_at,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO auth_invites "
                    "(token, user_id, channel, channel_id, created_by, created_at, expires_at, used_at) "
                    "VALUES (:token, :user_id, :channel, :channel_id, :created_by, "
                    ":created_at, :expires_at, NULL)"
                ),
                {
                    "token": token,
                    "user_id": user_id,
                    "channel": channel,
                    "channel_id": channel_id,
                    "created_by": created_by,
                    "created_at": created_at,
                    "expires_at": expires_at,
                },
            )
        return token

    def revoke(self, channel: str, channel_id: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM auth_identities "
                    "WHERE channel=:channel AND channel_id=:channel_id"
                ),
                {"channel": channel, "channel_id": channel_id},
            )
            return result.rowcount > 0

    def list_identities(self) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT i.channel, i.channel_id, i.user_id, u.display_name, i.linked_at "
                    "FROM auth_identities i "
                    "JOIN auth_users u ON u.user_id = i.user_id "
                    "ORDER BY i.linked_at"
                )
            ).fetchall()
        return [
            {
                "channel": r[0],
                "channel_id": r[1],
                "user_id": r[2],
                "display_name": r[3],
                "linked_at": r[4],
            }
            for r in rows
        ]

    _INVITE_SELECT = (
        "SELECT user_id, channel, channel_id, expires_at, used_at "
        "FROM auth_invites WHERE token=:token"
    )

    def redeem_invite(
        self, token: str, channel: str, channel_id: str
    ) -> tuple[str, str] | None:
        # Dialect-specific locking: SQLite uses BEGIN IMMEDIATE (write lock from
        # the first statement); Postgres uses SELECT ... FOR UPDATE on the row.
        if self._engine.dialect.name == "sqlite":
            with self._engine.connect() as conn:
                conn.execute(text("BEGIN IMMEDIATE"))
                result = self._redeem(
                    conn, self._INVITE_SELECT, token, channel, channel_id
                )
                conn.execute(text("COMMIT"))
                return result
        with self._engine.connect() as conn:
            result = self._redeem(
                conn, self._INVITE_SELECT + " FOR UPDATE", token, channel, channel_id
            )
            conn.commit()
            return result

    def _redeem(
        self, conn, select_q: str, token: str, channel: str, channel_id: str
    ) -> tuple[str, str] | None:
        row = conn.execute(text(select_q), {"token": token}).one_or_none()
        if row is None:
            return None
        user_id, bound_channel, bound_channel_id, expires_at, used_at = row
        if used_at is not None:
            return None
        if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            return None
        if bound_channel is not None and bound_channel != channel:
            return None
        if bound_channel_id is not None and bound_channel_id != channel_id:
            return None
        already = conn.execute(
            text(
                "SELECT 1 FROM auth_identities "
                "WHERE channel=:channel AND channel_id=:channel_id"
            ),
            {"channel": channel, "channel_id": channel_id},
        ).one_or_none()
        if already is not None:
            return None
        now = _now()
        conn.execute(
            text(
                "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                "VALUES (:channel, :channel_id, :user_id, :linked_at)"
            ),
            {
                "channel": channel,
                "channel_id": channel_id,
                "user_id": user_id,
                "linked_at": now,
            },
        )
        conn.execute(
            text("UPDATE auth_invites SET used_at=:now WHERE token=:token"),
            {"now": now, "token": token},
        )
        display_name = conn.execute(
            text("SELECT display_name FROM auth_users WHERE user_id=:user_id"),
            {"user_id": user_id},
        ).scalar_one()
        return (user_id, display_name)

    def bootstrap_admin(self, display_name: str, channel: str, channel_id: str) -> str:
        dialect = self._engine.dialect.name
        if dialect == "sqlite":
            with self._engine.connect() as conn:
                conn.execute(text("BEGIN IMMEDIATE"))
                if (
                    conn.execute(text("SELECT 1 FROM auth_users LIMIT 1")).one_or_none()
                    is not None
                ):
                    raise RuntimeError("auth tables not empty — bootstrap refused")
                user_id = uuid.uuid4().hex
                now = _now()
                conn.execute(
                    text(
                        "INSERT INTO auth_users (user_id, display_name, created_at) "
                        "VALUES (:user_id, :display_name, :created_at)"
                    ),
                    {
                        "user_id": user_id,
                        "display_name": display_name,
                        "created_at": now,
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                        "VALUES (:channel, :channel_id, :user_id, :linked_at)"
                    ),
                    {
                        "channel": channel,
                        "channel_id": channel_id,
                        "user_id": user_id,
                        "linked_at": now,
                    },
                )
                conn.execute(text("COMMIT"))
                return user_id
        else:
            with self._engine.connect() as conn:
                conn.execute(text("LOCK TABLE auth_users IN ACCESS EXCLUSIVE MODE"))
                if (
                    conn.execute(text("SELECT 1 FROM auth_users LIMIT 1")).one_or_none()
                    is not None
                ):
                    raise RuntimeError("auth tables not empty — bootstrap refused")
                user_id = uuid.uuid4().hex
                now = _now()
                conn.execute(
                    text(
                        "INSERT INTO auth_users (user_id, display_name, created_at) "
                        "VALUES (:user_id, :display_name, :created_at)"
                    ),
                    {
                        "user_id": user_id,
                        "display_name": display_name,
                        "created_at": now,
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                        "VALUES (:channel, :channel_id, :user_id, :linked_at)"
                    ),
                    {
                        "channel": channel,
                        "channel_id": channel_id,
                        "user_id": user_id,
                        "linked_at": now,
                    },
                )
                conn.commit()
                return user_id

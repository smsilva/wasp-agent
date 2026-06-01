import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import psycopg


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_DDL = (
    """
    CREATE TABLE IF NOT EXISTS auth_users (
      user_id      TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      created_at   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_identities (
      channel     TEXT NOT NULL,
      channel_id  TEXT NOT NULL,
      user_id     TEXT NOT NULL REFERENCES auth_users(user_id),
      linked_at   TEXT NOT NULL,
      PRIMARY KEY (channel, channel_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS auth_identities_user_idx
      ON auth_identities(user_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_invites (
      token       TEXT PRIMARY KEY,
      user_id     TEXT NOT NULL REFERENCES auth_users(user_id),
      channel     TEXT,
      channel_id  TEXT,
      created_by  TEXT NOT NULL,
      created_at  TEXT NOT NULL,
      expires_at  TEXT NOT NULL,
      used_at     TEXT
    )
    """,
)


class PostgresAuthRepository:
    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn if dsn is not None else os.environ["DATABASE_URL"]
        self._initialized = False

    def _conn(self) -> psycopg.Connection:
        self._ensure_initialized()
        return psycopg.connect(self._dsn)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with psycopg.connect(self._dsn) as con:
            for stmt in _DDL:
                con.execute(stmt)
            con.commit()
        self._initialized = True

    def init_schema(self) -> None:
        self._ensure_initialized()

    def is_authorized(self, channel: str, channel_id: str) -> str | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT user_id FROM auth_identities WHERE channel=%s AND channel_id=%s",
                (channel, channel_id),
            ).fetchone()
            return row[0] if row else None

    def create_user(self, display_name: str) -> str:
        user_id = uuid.uuid4().hex
        with self._conn() as con:
            con.execute(
                "INSERT INTO auth_users (user_id, display_name, created_at) "
                "VALUES (%s, %s, %s)",
                (user_id, display_name, _now()),
            )
            con.commit()
        return user_id

    def link_identity(self, user_id: str, channel: str, channel_id: str) -> None:
        with self._conn() as con:
            con.execute(
                "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                "VALUES (%s, %s, %s, %s)",
                (channel, channel_id, user_id, _now()),
            )
            con.commit()

    def has_any_user(self) -> bool:
        with self._conn() as con:
            row = con.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone()
            return row is not None

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
        with self._conn() as con:
            con.execute(
                "INSERT INTO auth_users (user_id, display_name, created_at) "
                "VALUES (%s, %s, %s)",
                (user_id, display_name, created_at),
            )
            con.execute(
                "INSERT INTO auth_invites "
                "(token, user_id, channel, channel_id, created_by, created_at, expires_at, used_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)",
                (
                    token,
                    user_id,
                    channel,
                    channel_id,
                    created_by,
                    created_at,
                    expires_at,
                ),
            )
        return token

    def redeem_invite(
        self, token: str, channel: str, channel_id: str
    ) -> tuple[str, str] | None:
        with self._conn() as con:
            # SELECT ... FOR UPDATE locks the invite row for the transaction,
            # so two concurrent callers serialize: the second blocks until the
            # first commits, then sees used_at set and returns None.
            row = con.execute(
                "SELECT user_id, channel, channel_id, expires_at, used_at "
                "FROM auth_invites WHERE token=%s FOR UPDATE",
                (token,),
            ).fetchone()
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
            already = con.execute(
                "SELECT 1 FROM auth_identities WHERE channel=%s AND channel_id=%s",
                (channel, channel_id),
            ).fetchone()
            if already is not None:
                return None
            now = _now()
            con.execute(
                "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                "VALUES (%s, %s, %s, %s)",
                (channel, channel_id, user_id, now),
            )
            con.execute(
                "UPDATE auth_invites SET used_at=%s WHERE token=%s", (now, token)
            )
            display_name = con.execute(
                "SELECT display_name FROM auth_users WHERE user_id=%s", (user_id,)
            ).fetchone()[0]
            return (user_id, display_name)

    def revoke(self, channel: str, channel_id: str) -> bool:
        with self._conn() as con:
            cur = con.execute(
                "DELETE FROM auth_identities WHERE channel=%s AND channel_id=%s",
                (channel, channel_id),
            )
            rowcount = cur.rowcount
            con.commit()
            return rowcount > 0

    def list_identities(self) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT i.channel, i.channel_id, i.user_id, u.display_name, i.linked_at "
                "FROM auth_identities i "
                "JOIN auth_users u ON u.user_id = i.user_id "
                "ORDER BY i.linked_at"
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

    def bootstrap_admin(self, display_name: str, channel: str, channel_id: str) -> str:
        with self._conn() as con:
            # ACCESS EXCLUSIVE lock is the Postgres equivalent of SQLite's
            # BEGIN IMMEDIATE: check + insert are atomic, preventing concurrent
            # bootstrap calls from creating orphan auth_users rows.
            con.execute("LOCK TABLE auth_users IN ACCESS EXCLUSIVE MODE")
            if con.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone() is not None:
                raise RuntimeError("auth tables not empty — bootstrap refused")
            user_id = uuid.uuid4().hex
            now = _now()
            con.execute(
                "INSERT INTO auth_users (user_id, display_name, created_at) "
                "VALUES (%s, %s, %s)",
                (user_id, display_name, now),
            )
            con.execute(
                "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                "VALUES (%s, %s, %s, %s)",
                (channel, channel_id, user_id, now),
            )
            return user_id

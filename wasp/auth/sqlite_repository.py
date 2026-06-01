import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from wasp.auth._connection import _connect, _now, _resolve_db_file
from wasp.auth._schema import init_schema


class SqliteAuthRepository:
    def __init__(self, db_file: str | None = None) -> None:
        self._db_file = _resolve_db_file(db_file)
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        init_schema(self._db_file)
        self._initialized = True

    def _conn(self) -> sqlite3.Connection:
        self._ensure_initialized()
        return _connect(self._db_file)

    def init_schema(self) -> None:
        self._ensure_initialized()

    def is_authorized(self, channel: str, channel_id: str) -> str | None:
        con = self._conn()
        try:
            row = con.execute(
                "SELECT user_id FROM auth_identities WHERE channel=? AND channel_id=?",
                (channel, channel_id),
            ).fetchone()
            return row[0] if row else None
        finally:
            con.close()

    def create_user(self, display_name: str) -> str:
        user_id = uuid.uuid4().hex
        con = self._conn()
        try:
            con.execute(
                "INSERT INTO auth_users (user_id, display_name, created_at) VALUES (?, ?, ?)",
                (user_id, display_name, _now()),
            )
            con.commit()
        finally:
            con.close()
        return user_id

    def link_identity(self, user_id: str, channel: str, channel_id: str) -> None:
        con = self._conn()
        try:
            con.execute(
                "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                "VALUES (?, ?, ?, ?)",
                (channel, channel_id, user_id, _now()),
            )
            con.commit()
        finally:
            con.close()

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
        con = self._conn()
        try:
            with con:
                con.execute(
                    "INSERT INTO auth_users (user_id, display_name, created_at) VALUES (?, ?, ?)",
                    (user_id, display_name, created_at),
                )
                con.execute(
                    "INSERT INTO auth_invites "
                    "(token, user_id, channel, channel_id, created_by, created_at, expires_at, used_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
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
        finally:
            con.close()
        return token

    def redeem_invite(
        self, token: str, channel: str, channel_id: str
    ) -> tuple[str, str] | None:
        con = self._conn()
        try:
            # BEGIN IMMEDIATE acquires the write lock before the SELECT, preventing
            # two concurrent callers from both seeing used_at=NULL and both succeeding.
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT user_id, channel, channel_id, expires_at, used_at "
                "FROM auth_invites WHERE token=?",
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
            # Reject if (channel, channel_id) is already linked to a user. Leave
            # the invite unconsumed so the admin can revoke the existing identity
            # and the invite can be retried.
            already = con.execute(
                "SELECT 1 FROM auth_identities WHERE channel=? AND channel_id=?",
                (channel, channel_id),
            ).fetchone()
            if already is not None:
                return None
            now = _now()
            with con:
                con.execute(
                    "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                    "VALUES (?, ?, ?, ?)",
                    (channel, channel_id, user_id, now),
                )
                con.execute(
                    "UPDATE auth_invites SET used_at=? WHERE token=?", (now, token)
                )
            display_name = con.execute(
                "SELECT display_name FROM auth_users WHERE user_id=?", (user_id,)
            ).fetchone()[0]
            return (user_id, display_name)
        finally:
            con.close()

    def revoke(self, channel: str, channel_id: str) -> bool:
        con = self._conn()
        try:
            cur = con.execute(
                "DELETE FROM auth_identities WHERE channel=? AND channel_id=?",
                (channel, channel_id),
            )
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()

    def list_identities(self) -> list[dict]:
        con = self._conn()
        try:
            rows = con.execute(
                "SELECT i.channel, i.channel_id, i.user_id, u.display_name, i.linked_at "
                "FROM auth_identities i "
                "JOIN auth_users u ON u.user_id = i.user_id "
                "ORDER BY i.linked_at"
            ).fetchall()
        finally:
            con.close()
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

    def has_any_user(self) -> bool:
        con = self._conn()
        try:
            row = con.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone()
            return row is not None
        finally:
            con.close()

    def bootstrap_admin(self, display_name: str, channel: str, channel_id: str) -> str:
        con = self._conn()
        try:
            # Single IMMEDIATE transaction: check + insert are atomic, preventing
            # concurrent bootstrap calls from creating orphan auth_users rows.
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone() is not None:
                raise RuntimeError("auth tables not empty — bootstrap refused")
            user_id = uuid.uuid4().hex
            now = _now()
            with con:
                con.execute(
                    "INSERT INTO auth_users (user_id, display_name, created_at) VALUES (?, ?, ?)",
                    (user_id, display_name, now),
                )
                con.execute(
                    "INSERT INTO auth_identities (channel, channel_id, user_id, linked_at) "
                    "VALUES (?, ?, ?, ?)",
                    (channel, channel_id, user_id, now),
                )
            return user_id
        finally:
            con.close()

"""Multi-channel identity and invite-based authorization.

Storage is SQLite via stdlib `sqlite3`. Each operation opens its own
connection (cheap on a local file) and enables foreign keys per connection.
`init_db` is idempotent and invoked lazily by every public function.
"""

import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

_initialized_dbs: set[str] = set()

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


def _resolve_db_file(db_file: str | None) -> str:
    if db_file is not None:
        return db_file
    return os.getenv("WASP_AGENT_DB_FILE", "agent.db")


def _connect(db_file: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_file)
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(db_file: str | None = None) -> None:
    """Create schema. Idempotent."""
    db_file = _resolve_db_file(db_file)
    if db_file in _initialized_dbs:
        return
    con = _connect(db_file)
    try:
        for stmt in _DDL:
            con.execute(stmt)
        con.commit()
    finally:
        con.close()
    _initialized_dbs.add(db_file)


def is_authorized(
    channel: str, channel_id: str, db_file: str | None = None
) -> str | None:
    db_file = _resolve_db_file(db_file)
    init_db(db_file)
    con = _connect(db_file)
    try:
        row = con.execute(
            "SELECT user_id FROM auth_identities WHERE channel=? AND channel_id=?",
            (channel, channel_id),
        ).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def create_user(display_name: str, db_file: str | None = None) -> str:
    db_file = _resolve_db_file(db_file)
    init_db(db_file)
    user_id = uuid.uuid4().hex
    con = _connect(db_file)
    try:
        con.execute(
            "INSERT INTO auth_users (user_id, display_name, created_at) VALUES (?, ?, ?)",
            (user_id, display_name, _now()),
        )
        con.commit()
    finally:
        con.close()
    return user_id


def link_identity(
    user_id: str,
    channel: str,
    channel_id: str,
    db_file: str | None = None,
) -> None:
    db_file = _resolve_db_file(db_file)
    init_db(db_file)
    con = _connect(db_file)
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
    display_name: str,
    created_by: str,
    channel: str | None = None,
    channel_id: str | None = None,
    db_file: str | None = None,
) -> str:
    db_file = _resolve_db_file(db_file)
    init_db(db_file)
    ttl_hours = int(os.getenv("WASP_AGENT_INVITE_TTL_HOURS", "1"))
    user_id = uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
    con = _connect(db_file)
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
    token: str,
    channel: str,
    channel_id: str,
    db_file: str | None = None,
) -> tuple[str, str] | None:
    db_file = _resolve_db_file(db_file)
    init_db(db_file)
    con = _connect(db_file)
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
            con.execute("UPDATE auth_invites SET used_at=? WHERE token=?", (now, token))
        display_name = con.execute(
            "SELECT display_name FROM auth_users WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        return (user_id, display_name)
    finally:
        con.close()


def revoke(channel: str, channel_id: str, db_file: str | None = None) -> bool:
    db_file = _resolve_db_file(db_file)
    init_db(db_file)
    con = _connect(db_file)
    try:
        cur = con.execute(
            "DELETE FROM auth_identities WHERE channel=? AND channel_id=?",
            (channel, channel_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def list_identities(db_file: str | None = None) -> list[dict]:
    db_file = _resolve_db_file(db_file)
    init_db(db_file)
    con = _connect(db_file)
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


def bootstrap_admin(
    display_name: str,
    channel: str,
    channel_id: str,
    db_file: str | None = None,
) -> str:
    db_file = _resolve_db_file(db_file)
    init_db(db_file)
    con = _connect(db_file)
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


def has_any_user(db_file: str | None = None) -> bool:
    db_file = _resolve_db_file(db_file)
    init_db(db_file)
    con = _connect(db_file)
    try:
        row = con.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone()
        return row is not None
    finally:
        con.close()

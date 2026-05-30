from wasp.auth._connection import _connect

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


def init_schema(db_file: str) -> None:
    con = _connect(db_file)
    try:
        for stmt in _DDL:
            con.execute(stmt)
        con.commit()
    finally:
        con.close()

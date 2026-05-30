import os
import sqlite3
from datetime import datetime, timezone


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

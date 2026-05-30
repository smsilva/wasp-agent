import os


def build_session_db():
    backend = os.getenv("DATABASE_BACKEND", "sqlite")
    if backend == "sqlite":
        from agno.db.sqlite.sqlite import SqliteDb

        return SqliteDb(
            db_file=os.getenv("DATABASE_FILE", "agent.db"),
            session_table="agent_sessions",
        )
    raise ValueError(f"unsupported backend: {backend}")

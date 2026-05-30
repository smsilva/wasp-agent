import os


def build_session_db():
    backend = os.getenv("DATABASE_BACKEND", "sqlite")
    if backend == "sqlite":
        from agno.db.sqlite.sqlite import SqliteDb

        return SqliteDb(
            db_file=os.getenv("DATABASE_FILE", "agent.db"),
            session_table="agent_sessions",
        )
    elif backend == "postgres":
        try:
            from agno.db.postgres import PostgresDb
        except ImportError as e:
            raise NotImplementedError(
                "Postgres backend for agno sessions not yet wired. "
                "See docs/sdlc/02-design/2026-05-30-postgres-readiness.md"
            ) from e
        return PostgresDb(db_url=os.environ["DATABASE_URL"])  # pragma: no cover
    raise ValueError(f"unsupported backend: {backend}")

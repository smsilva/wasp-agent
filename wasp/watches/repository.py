from datetime import datetime, timezone

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from wasp.db import get_engine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WatchRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else get_engine()

    def init_schema(self) -> None:
        from wasp.watches._schema import init_schema as _init_schema

        _init_schema(self._engine)

    def register(self, kind: str, name: str, session_id: str) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO resource_watches "
                        "(kind, name, session_id, status, created_at) "
                        "VALUES (:kind, :name, :session_id, 'pending', :created_at)"
                    ),
                    {
                        "kind": kind,
                        "name": name,
                        "session_id": session_id,
                        "created_at": _now(),
                    },
                )
        except IntegrityError:
            pass

    def _set_status(
        self, kind: str, name: str, status: str, notified_at: str | None = None
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE resource_watches SET status=:status, notified_at=:notified_at "
                    "WHERE kind=:kind AND name=:name"
                ),
                {
                    "status": status,
                    "notified_at": notified_at,
                    "kind": kind,
                    "name": name,
                },
            )

    def complete(self, kind: str, name: str) -> None:
        self._set_status(kind, name, "ready", _now())

    def fail(self, kind: str, name: str) -> None:
        self._set_status(kind, name, "failed")

    def timeout(self, kind: str, name: str) -> None:
        self._set_status(kind, name, "timeout")

    def list_pending(self) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT kind, name, session_id FROM resource_watches "
                    "WHERE status='pending'"
                )
            ).fetchall()
        return [{"kind": r[0], "name": r[1], "session_id": r[2]} for r in rows]

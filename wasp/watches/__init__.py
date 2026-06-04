import logging
import threading

log = logging.getLogger(__name__)

_repository = None


def get_repository():
    global _repository
    if _repository is None:
        from wasp.watches.repository import WatchRepository

        r = WatchRepository()
        r.init_schema()
        _repository = r
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None


def restore_pending_watches() -> None:
    from wasp.watcher import (
        _select_notifier,
        watch_cluster,
        watch_platform,
    )  # lazy — avoids circular import

    for watch in get_repository().list_pending():
        kind = watch["kind"]
        name = watch["name"]
        session_id = watch["session_id"]

        parts = session_id.split(":")
        if len(parts) < 3 or parts[0] not in ("tg", "local", "dc"):
            log.warning(
                "restore: malformed session_id %r for %s/%s — skipping",
                session_id,
                kind,
                name,
            )
            continue

        channel = parts[0]
        chat_id = parts[2]

        notifier = _select_notifier(channel)
        if notifier is None:
            log.warning(
                "restore: no notifier for channel %r — skipping %s/%s",
                channel,
                kind,
                name,
            )
            continue

        if kind == "Platform":
            coro_fn = watch_platform
        elif kind == "Cluster":
            coro_fn = watch_cluster
        else:
            log.warning("restore: unknown kind %r — skipping %s/%s", kind, kind, name)
            continue

        log.info("Restoring watch for %s/%s", kind, name)

        def _run(fn=coro_fn, n=name, c=chat_id, nf=notifier):
            import asyncio

            asyncio.run(fn(n, c, nf))

        threading.Thread(target=_run, daemon=True).start()

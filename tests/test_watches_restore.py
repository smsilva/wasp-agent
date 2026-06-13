import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
def engine(tmp_path):
    e = create_engine(
        f"sqlite:///{tmp_path / 'watches.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    yield e
    e.dispose()


def test_get_repository_returns_singleton(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "w.db"))
    from wasp.db import _reset_engine
    from wasp.watches import _reset_repository, get_repository

    _reset_repository()
    _reset_engine()
    a = get_repository()
    b = get_repository()
    assert a is b
    _reset_repository()
    _reset_engine()


def test_restore_spawns_thread_for_pending_platform(engine, monkeypatch):
    from wasp.watches.repository import WatchRepository

    repo = WatchRepository(engine=engine)
    repo.init_schema()
    repo.register("Platform", "my-platform", "tg:agent:12345")

    spawned = []

    def fake_thread(target=None, daemon=None):
        m = MagicMock()
        spawned.append(target)
        return m

    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock()
    fake_coro = MagicMock(name="watch_platform_coro")
    asyncio_run = MagicMock(name="asyncio.run")

    with (
        patch("wasp.watches.get_repository", return_value=repo),
        patch("wasp.watches.threading.Thread", side_effect=fake_thread),
        patch("wasp.watcher._select_notifier", return_value=mock_notifier),
        # `watch_platform` is `async def`; pass `new=MagicMock(...)` to avoid
        # patch()'s automatic AsyncMock substitution (which would wrap the
        # return value in a coroutine instead of handing it to asyncio.run).
        patch("wasp.watcher.watch_platform", new=MagicMock(return_value=fake_coro)),
        patch("asyncio.run", asyncio_run),
    ):
        from wasp.watches import restore_pending_watches

        restore_pending_watches()
        # Execute the captured thread target to cover the inner `_run` closure.
        spawned[0]()

    assert len(spawned) == 1
    asyncio_run.assert_called_once_with(fake_coro)


def test_restore_spawns_thread_for_pending_cluster(engine, monkeypatch):
    from wasp.watches.repository import WatchRepository

    repo = WatchRepository(engine=engine)
    repo.init_schema()
    repo.register("Cluster", "edge", "tg:agent:12345")

    spawned = []

    def fake_thread(target=None, daemon=None):
        m = MagicMock()
        spawned.append(target)
        return m

    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock()
    fake_coro = MagicMock(name="watch_cluster_coro")
    asyncio_run = MagicMock(name="asyncio.run")

    with (
        patch("wasp.watches.get_repository", return_value=repo),
        patch("wasp.watches.threading.Thread", side_effect=fake_thread),
        patch("wasp.watcher._select_notifier", return_value=mock_notifier),
        patch("wasp.watcher.watch_cluster", new=MagicMock(return_value=fake_coro)),
        patch("asyncio.run", asyncio_run),
    ):
        from wasp.watches import restore_pending_watches

        restore_pending_watches()
        # Execute the captured thread target to cover the inner `_run` closure.
        spawned[0]()

    assert len(spawned) == 1
    asyncio_run.assert_called_once_with(fake_coro)


def test_restore_skips_watch_with_no_notifier(engine):
    from wasp.watches.repository import WatchRepository

    repo = WatchRepository(engine=engine)
    repo.init_schema()
    repo.register("Platform", "p1", "tg:agent:12345")

    with (
        patch("wasp.watches.get_repository", return_value=repo),
        patch("wasp.watcher._select_notifier", return_value=None),
    ):
        from wasp.watches import restore_pending_watches

        restore_pending_watches()


def test_restore_skips_unknown_kind(engine, caplog):
    from wasp.watches.repository import WatchRepository

    repo = WatchRepository(engine=engine)
    repo.init_schema()
    repo.register("Unknown", "x", "tg:agent:1")

    with caplog.at_level(logging.WARNING, logger="wasp.watches"):
        with (
            patch("wasp.watches.get_repository", return_value=repo),
            patch("wasp.watcher._select_notifier", return_value=MagicMock()),
        ):
            from wasp.watches import restore_pending_watches

            restore_pending_watches()

    assert "skipping Unknown/x" in caplog.text


def test_restore_handles_malformed_session_id(engine):
    from wasp.watches.repository import WatchRepository

    repo = WatchRepository(engine=engine)
    repo.init_schema()
    repo.register("Platform", "p1", "bad-session-id")

    with patch("wasp.watches.get_repository", return_value=repo):
        from wasp.watches import restore_pending_watches

        restore_pending_watches()

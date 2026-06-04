import asyncio
from unittest.mock import AsyncMock, MagicMock


def test_cluster_ready_message_includes_version():
    from wasp.watcher import cluster_ready_message

    cluster = {"spec": {"kubernetesVersion": "1.34"}}
    msg = cluster_ready_message("edge", cluster)

    assert "edge" in msg
    assert "1.34" in msg


def test_watch_cluster_notifies_when_ready(monkeypatch):
    from wasp import watcher

    mock_api = MagicMock()
    mock_api.get_cluster_custom_object.return_value = {
        "spec": {"kubernetesVersion": "1.34"},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(watcher, "load_kube_config_auto", lambda: mock_api)

    notifier = MagicMock()
    notifier.send = AsyncMock()

    asyncio.run(watcher.watch_cluster("edge", "chat-1", notifier))

    notifier.send.assert_awaited_once()
    sent = notifier.send.await_args.args[1]
    assert "edge" in sent
    assert "1.34" in sent


def test_cluster_watcher_spawner_skips_without_chat_id():
    from wasp.watcher import ClusterWatcherSpawner

    spawned = ClusterWatcherSpawner().spawn(
        name="edge", chat_id=None, channel="tg", parent_span_ctx=None
    )

    assert spawned is False


def test_cluster_watcher_spawner_starts_thread(monkeypatch):
    from wasp import watcher
    from wasp.watcher import ClusterWatcherSpawner

    mock_thread = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread)
    monkeypatch.setattr(watcher.threading, "Thread", mock_thread_cls)
    monkeypatch.setattr(watcher, "_select_notifier", lambda channel: MagicMock())

    spawned = ClusterWatcherSpawner().spawn(
        name="edge", chat_id="chat-1", channel="local", parent_span_ctx=None
    )

    assert spawned is True
    mock_thread.start.assert_called_once()


def test_cluster_watcher_spawner_skips_without_notifier(monkeypatch):
    from wasp import watcher
    from wasp.watcher import ClusterWatcherSpawner

    monkeypatch.setattr(watcher, "_select_notifier", lambda channel: None)

    spawned = ClusterWatcherSpawner().spawn(
        name="edge", chat_id="chat-1", channel="tg", parent_span_ctx=None
    )

    assert spawned is False


def test_watch_cluster_logs_exception_and_does_not_raise(monkeypatch):
    from wasp import watcher

    mock_api = MagicMock()
    mock_api.get_cluster_custom_object.side_effect = RuntimeError("boom")
    monkeypatch.setattr(watcher, "load_kube_config_auto", lambda: mock_api)

    notifier = MagicMock()
    notifier.send = AsyncMock()

    asyncio.run(watcher.watch_cluster("edge", "chat-1", notifier))

    notifier.send.assert_not_awaited()


def test_watch_cluster_retries_on_404(monkeypatch):
    from wasp import watcher

    class FakeApiException(Exception):
        def __init__(self, status):
            self.status = status

    call_count = 0

    def fake_get(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise FakeApiException(status=404)
        return {
            "spec": {"kubernetesVersion": "1.34"},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }

    mock_api = MagicMock()
    mock_api.get_cluster_custom_object.side_effect = fake_get
    monkeypatch.setattr(watcher, "load_kube_config_auto", lambda: mock_api)
    monkeypatch.setattr(watcher, "ApiException", FakeApiException)
    monkeypatch.setattr(watcher.asyncio, "sleep", AsyncMock())

    notifier = MagicMock()
    notifier.send = AsyncMock()

    asyncio.run(watcher.watch_cluster("edge", "chat-1", notifier))

    notifier.send.assert_awaited_once()


def test_watch_cluster_sends_timeout_message(monkeypatch):
    from wasp import watcher

    mock_api = MagicMock()
    mock_api.get_cluster_custom_object.return_value = {
        "spec": {"kubernetesVersion": "1.34"},
        "status": {"conditions": [{"type": "Ready", "status": "False"}]},
    }
    monkeypatch.setattr(watcher, "load_kube_config_auto", lambda: mock_api)
    monkeypatch.setattr(watcher.asyncio, "sleep", AsyncMock())

    deadline_calls = iter([True, False])

    def fake_monotonic():
        try:
            if next(deadline_calls):
                return 0
            return watcher.WATCH_TIMEOUT_SECONDS + 1
        except StopIteration:
            return watcher.WATCH_TIMEOUT_SECONDS + 1

    monkeypatch.setattr(watcher.time, "monotonic", fake_monotonic)

    notifier = MagicMock()
    notifier.send = AsyncMock()

    asyncio.run(watcher.watch_cluster("edge", "chat-1", notifier))

    notifier.send.assert_awaited_once()
    msg = notifier.send.await_args.args[1]
    assert "10 minutos" in msg


def test_watch_cluster_with_valid_parent_span_ctx(monkeypatch):
    from wasp import watcher

    mock_api = MagicMock()
    mock_api.get_cluster_custom_object.return_value = {
        "spec": {"kubernetesVersion": "1.34"},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(watcher, "load_kube_config_auto", lambda: mock_api)

    mock_span_ctx = MagicMock()
    mock_span_ctx.is_valid = True

    notifier = MagicMock()
    notifier.send = AsyncMock()

    asyncio.run(watcher.watch_cluster("edge", "chat-1", notifier, mock_span_ctx))

    notifier.send.assert_awaited_once()


def test_cluster_watcher_spawner_thread_runs_asyncio(monkeypatch):
    from wasp import watcher
    from wasp.watcher import ClusterWatcherSpawner

    captured = {}

    class FakeThread:
        def __init__(self, target, daemon):
            captured["target"] = target

        def start(self):
            pass

    monkeypatch.setattr(watcher.threading, "Thread", FakeThread)
    monkeypatch.setattr(watcher, "_select_notifier", lambda channel: MagicMock())
    monkeypatch.setattr(watcher.asyncio, "run", MagicMock())

    ClusterWatcherSpawner().spawn(
        name="edge", chat_id="chat-1", channel="local", parent_span_ctx=None
    )

    captured["target"]()
    watcher.asyncio.run.assert_called_once()

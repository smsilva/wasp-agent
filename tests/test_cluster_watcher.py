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
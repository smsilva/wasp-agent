def test_extract_chat_id_from_telegram_session():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    assert extract_chat_id(FakeCtx()) == "5621932873"


def test_extract_chat_id_returns_none_for_non_telegram():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "web:abc:def"

    class EmptyCtx:
        session_id = ""

    assert extract_chat_id(FakeCtx()) is None
    assert extract_chat_id(None) is None
    assert extract_chat_id(EmptyCtx()) is None


def test_ready_message_includes_endpoints():
    from tools.watcher import ready_message

    platform = {
        "spec": {
            "regions": [
                {"name": "us-east-1", "endpoint": "gateway.us-east-1.wp2.wasp.silvios.me"},
                {"name": "sa-east-1", "endpoint": "gateway.sa-east-1.wp2.wasp.silvios.me"},
            ]
        }
    }
    msg = ready_message("wp2", platform)
    assert "wp2" in msg
    assert "us-east-1" in msg
    assert "https://gateway.us-east-1.wp2.wasp.silvios.me" in msg
    assert "https://gateway.sa-east-1.wp2.wasp.silvios.me" in msg


def test_load_kube_config_auto_incluster(monkeypatch):
    from unittest.mock import MagicMock
    import tools.watcher as w

    incluster = MagicMock()
    local = MagicMock()
    monkeypatch.setattr(w.config, "load_incluster_config", incluster)
    monkeypatch.setattr(w.config, "load_kube_config", local)

    w.load_kube_config_auto()

    incluster.assert_called_once()
    local.assert_not_called()


def test_load_kube_config_auto_fallback_local(monkeypatch):
    from unittest.mock import MagicMock
    import tools.watcher as w

    class FakeConfigException(Exception):
        pass

    # ConfigException must be a real Exception subclass for raise/except to work with mocked module
    monkeypatch.setattr(w.config, "ConfigException", FakeConfigException)

    def raise_(*a, **kw):
        raise FakeConfigException("not in cluster")

    incluster = MagicMock(side_effect=raise_)
    local = MagicMock()
    monkeypatch.setattr(w.config, "load_incluster_config", incluster)
    monkeypatch.setattr(w.config, "load_kube_config", local)

    w.load_kube_config_auto()

    incluster.assert_called_once()
    local.assert_called_once()


async def test_notify_telegram_posts_message(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False
    cm = MagicMock(return_value=fake_client)
    monkeypatch.setattr(w.httpx, "AsyncClient", cm)

    await w.notify_telegram("12345", "fake-token", "hello")

    cm.assert_called_once()
    fake_client.post.assert_awaited_once_with(
        "https://api.telegram.org/botfake-token/sendMessage",
        json={"chat_id": "12345", "text": "hello"},
    )


async def test_watch_platform_notifies_when_ready(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w

    api = MagicMock()
    api.get_cluster_custom_object.return_value = {
        "spec": {"regions": [{"name": "us-east-1", "endpoint": "gateway.us-east-1.wp2.wasp.silvios.me"}]},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    notify = AsyncMock()
    monkeypatch.setattr(w, "notify_telegram", notify)

    await w.watch_platform("wp2", "12345", "fake-token")

    notify.assert_awaited_once()
    args = notify.await_args.args
    assert args[0] == "12345"
    assert "wp2" in args[2]
    assert "https://gateway.us-east-1.wp2.wasp.silvios.me" in args[2]


async def test_watch_platform_retries_on_404_until_timeout(monkeypatch):
    from itertools import chain, repeat
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w

    class FakeApiException(Exception):
        def __init__(self, status, reason):
            self.status = status
            self.reason = reason

    monkeypatch.setattr(w, "ApiException", FakeApiException)

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = FakeApiException(status=404, reason="NotFound")
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    notify = AsyncMock()
    monkeypatch.setattr(w, "notify_telegram", notify)
    monkeypatch.setattr(w.asyncio, "sleep", AsyncMock())

    # [0, 0]: first for deadline calc, second for while condition (enters loop once)
    # then repeat(601): exits loop on next while check
    times = chain([0, 0], repeat(w.WATCH_TIMEOUT_SECONDS + 1))
    monkeypatch.setattr(w.time, "monotonic", lambda: next(times))

    await w.watch_platform("wp2", "12345", "fake-token")

    notify.assert_awaited_once()
    assert "10 minutos" in notify.await_args.args[2]


async def test_watch_platform_timeout(monkeypatch):
    from itertools import chain, repeat
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w

    api = MagicMock()
    api.get_cluster_custom_object.return_value = {"status": {"conditions": []}}
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    notify = AsyncMock()
    monkeypatch.setattr(w, "notify_telegram", notify)

    monkeypatch.setattr(w.asyncio, "sleep", AsyncMock())
    # First call returns 0 (deadline = 600), all subsequent calls return 601 (> deadline → exit loop).
    # Use repeat so teardown calls to time.monotonic() don't exhaust the iterator.
    times = chain([0], repeat(w.WATCH_TIMEOUT_SECONDS + 1))
    monkeypatch.setattr(w.time, "monotonic", lambda: next(times))

    await w.watch_platform("wp2", "12345", "fake-token")

    notify.assert_awaited_once()
    assert "10 minutos" in notify.await_args.args[2]


def test_find_condition_returns_none_when_not_found():
    from tools.watcher import _find_condition

    assert _find_condition({"status": {"conditions": [{"type": "Synced", "status": "True"}]}}, "Ready") is None
    assert _find_condition({}, "Ready") is None


async def test_watch_platform_reraises_non_404_exception(monkeypatch):
    from unittest.mock import MagicMock
    import tools.watcher as w

    class FakeApiException(Exception):
        def __init__(self, status, reason):
            self.status = status
            self.reason = reason

    monkeypatch.setattr(w, "ApiException", FakeApiException)

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = FakeApiException(status=500, reason="InternalServerError")
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)

    # Non-404 exceptions are caught, logged, and do not propagate from watch_platform
    await w.watch_platform("wp2", "12345", "fake-token")


async def test_watch_platform_retries_until_ready(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w

    api = MagicMock()
    not_ready = {"status": {"conditions": []}}
    ready = {
        "spec": {"regions": []},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    api.get_cluster_custom_object.side_effect = [not_ready, ready]
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    notify = AsyncMock()
    monkeypatch.setattr(w, "notify_telegram", notify)
    monkeypatch.setattr(w.asyncio, "sleep", AsyncMock())

    await w.watch_platform("wp2", "12345", "fake-token")

    assert api.get_cluster_custom_object.call_count == 2
    notify.assert_awaited_once()
    assert "pronta" in notify.await_args.args[2]

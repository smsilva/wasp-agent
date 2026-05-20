def test_extract_chat_id_from_agno_session_with_suffix():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "tg:wasp-agent:5621932873:8ec68b0f"

    assert extract_chat_id(FakeCtx()) == "5621932873"


def test_extract_chat_id_from_agno_session_no_suffix():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "tg:wasp-agent:5621932873"

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


async def test_telegram_notifier_send_posts_message(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import tools.notifier as n

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False
    cm = MagicMock(return_value=fake_client)
    monkeypatch.setattr(n.httpx, "AsyncClient", cm)

    notifier = n.TelegramNotifier(token="fake-token")
    await notifier.send("12345", "hello")

    cm.assert_called_once()
    fake_client.post.assert_awaited_once_with(
        "https://api.telegram.org/botfake-token/sendMessage",
        json={"chat_id": "12345", "text": "hello"},
    )


async def test_recording_notifier_captures_messages():
    from tools.notifier import RecordingNotifier

    n = RecordingNotifier()
    await n.send("123", "hello")
    await n.send("456", "world")

    assert n.messages == [
        {"chat_id": "123", "text": "hello"},
        {"chat_id": "456", "text": "world"},
    ]


async def test_watch_platform_notifies_when_ready(monkeypatch):
    from unittest.mock import MagicMock
    import tools.watcher as w
    from tools.notifier import RecordingNotifier

    api = MagicMock()
    api.get_cluster_custom_object.return_value = {
        "spec": {"regions": [{"name": "us-east-1", "endpoint": "gateway.us-east-1.wp2.wasp.silvios.me"}]},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    notifier = RecordingNotifier()

    await w.watch_platform("wp2", "12345", notifier)

    assert len(notifier.messages) == 1
    assert notifier.messages[0]["chat_id"] == "12345"
    assert "wp2" in notifier.messages[0]["text"]
    assert "https://gateway.us-east-1.wp2.wasp.silvios.me" in notifier.messages[0]["text"]


async def test_watch_platform_retries_on_404_until_timeout(monkeypatch):
    from itertools import chain, repeat
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w
    from tools.notifier import RecordingNotifier

    class FakeApiException(Exception):
        def __init__(self, status, reason):
            self.status = status
            self.reason = reason

    monkeypatch.setattr(w, "ApiException", FakeApiException)

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = FakeApiException(status=404, reason="NotFound")
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    monkeypatch.setattr(w.asyncio, "sleep", AsyncMock())

    times = chain([0, 0], repeat(w.WATCH_TIMEOUT_SECONDS + 1))
    monkeypatch.setattr(w.time, "monotonic", lambda: next(times))

    notifier = RecordingNotifier()
    await w.watch_platform("wp2", "12345", notifier)

    assert len(notifier.messages) == 1
    assert "10 minutos" in notifier.messages[0]["text"]


async def test_watch_platform_timeout(monkeypatch):
    from itertools import chain, repeat
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w
    from tools.notifier import RecordingNotifier

    api = MagicMock()
    api.get_cluster_custom_object.return_value = {"status": {"conditions": []}}
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)

    monkeypatch.setattr(w.asyncio, "sleep", AsyncMock())
    times = chain([0], repeat(w.WATCH_TIMEOUT_SECONDS + 1))
    monkeypatch.setattr(w.time, "monotonic", lambda: next(times))

    notifier = RecordingNotifier()
    await w.watch_platform("wp2", "12345", notifier)

    assert len(notifier.messages) == 1
    assert "10 minutos" in notifier.messages[0]["text"]


def test_find_condition_returns_none_when_not_found():
    from tools.watcher import _find_condition

    assert _find_condition({"status": {"conditions": [{"type": "Synced", "status": "True"}]}}, "Ready") is None
    assert _find_condition({}, "Ready") is None


async def test_watch_platform_reraises_non_404_exception(monkeypatch):
    from unittest.mock import MagicMock
    import tools.watcher as w
    from tools.notifier import RecordingNotifier

    class FakeApiException(Exception):
        def __init__(self, status, reason):
            self.status = status
            self.reason = reason

    monkeypatch.setattr(w, "ApiException", FakeApiException)

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = FakeApiException(status=500, reason="InternalServerError")
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)

    # Non-404 exceptions are caught, logged, and do not propagate from watch_platform
    await w.watch_platform("wp2", "12345", RecordingNotifier())


async def test_watcher_records_polls_counter(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from tools.notifier import RecordingNotifier
    import telemetry
    reader = InMemoryMetricReader()
    telemetry.configure(metric_reader=reader)

    import tools.watcher as w
    api = MagicMock()
    api.get_cluster_custom_object.return_value = {
        "spec": {"regions": []},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)

    await w.watch_platform("wp1", "123", RecordingNotifier())

    metrics_data = reader.get_metrics_data()
    metric_names = {
        m.name
        for rm in metrics_data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert "agent.watcher.polls.total" in metric_names


async def test_watcher_records_duration_on_ready(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from tools.notifier import RecordingNotifier
    import telemetry
    reader = InMemoryMetricReader()
    telemetry.configure(metric_reader=reader)

    import tools.watcher as w
    api = MagicMock()
    api.get_cluster_custom_object.return_value = {
        "spec": {"regions": []},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)

    await w.watch_platform("wp1", "123", RecordingNotifier())

    metrics_data = reader.get_metrics_data()
    metric_names = {
        m.name
        for rm in metrics_data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert "agent.watcher.duration_seconds" in metric_names


async def test_watcher_links_to_parent_span(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import SpanContext, TraceFlags
    from tools.notifier import RecordingNotifier
    import telemetry
    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    import tools.watcher as w
    api = MagicMock()
    api.get_cluster_custom_object.return_value = {
        "spec": {"regions": []},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)

    parent_ctx = SpanContext(
        trace_id=0x1234,
        span_id=0x5678,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    await w.watch_platform("wp1", "123", RecordingNotifier(), parent_ctx)

    spans = exporter.get_finished_spans()
    lifecycle = next(s for s in spans if s.name == "agent.watcher.lifecycle")
    assert len(lifecycle.links) == 1


async def test_watcher_creates_lifecycle_span(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from tools.notifier import RecordingNotifier
    import telemetry
    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    import tools.watcher as w
    api = MagicMock()
    api.get_cluster_custom_object.return_value = {
        "spec": {"regions": []},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)

    await w.watch_platform("wp1", "123", RecordingNotifier())

    spans = exporter.get_finished_spans()
    assert any(s.name == "agent.watcher.lifecycle" for s in spans)


async def test_watch_platform_retries_until_ready(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w
    from tools.notifier import RecordingNotifier

    api = MagicMock()
    not_ready = {"status": {"conditions": []}}
    ready = {
        "spec": {"regions": []},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    api.get_cluster_custom_object.side_effect = [not_ready, ready]
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    monkeypatch.setattr(w.asyncio, "sleep", AsyncMock())

    notifier = RecordingNotifier()
    await w.watch_platform("wp2", "12345", notifier)

    assert api.get_cluster_custom_object.call_count == 2
    assert len(notifier.messages) == 1
    assert "pronta" in notifier.messages[0]["text"]

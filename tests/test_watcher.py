def test_extract_chat_id_from_agno_session_with_suffix():
    from wasp.watcher import extract_chat_id

    class FakeCtx:
        session_id = "tg:wasp-agent:5621932873:8ec68b0f"

    assert extract_chat_id(FakeCtx()) == "5621932873"


def test_extract_chat_id_from_agno_session_no_suffix():
    from wasp.watcher import extract_chat_id

    class FakeCtx:
        session_id = "tg:wasp-agent:5621932873"

    assert extract_chat_id(FakeCtx()) == "5621932873"


def test_extract_chat_id_returns_none_for_non_telegram():
    from wasp.watcher import extract_chat_id

    class FakeCtx:
        session_id = "web:abc:def"

    class EmptyCtx:
        session_id = ""

    assert extract_chat_id(FakeCtx()) is None
    assert extract_chat_id(None) is None
    assert extract_chat_id(EmptyCtx()) is None


def test_extract_channel_returns_tg_for_telegram_session():
    from wasp.watcher import extract_channel

    class FakeCtx:
        session_id = "tg:wasp-agent:5621932873"

    assert extract_channel(FakeCtx()) == "tg"


def test_extract_channel_returns_local_for_local_session():
    from wasp.watcher import extract_channel

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    assert extract_channel(FakeCtx()) == "local"


def test_extract_channel_returns_none_for_other_sources():
    from wasp.watcher import extract_channel

    class WebCtx:
        session_id = "web:abc:def"

    class EmptyCtx:
        session_id = ""

    assert extract_channel(None) is None
    assert extract_channel(EmptyCtx()) is None
    assert extract_channel(WebCtx()) is None


def test_ready_message_includes_endpoints():
    from wasp.watcher import ready_message

    platform = {
        "spec": {
            "regions": [
                {
                    "name": "us-east-1",
                    "endpoint": "gateway.us-east-1.wp2.wasp.silvios.me",
                },
                {
                    "name": "sa-east-1",
                    "endpoint": "gateway.sa-east-1.wp2.wasp.silvios.me",
                },
            ]
        }
    }
    msg = ready_message("wp2", platform)
    assert "wp2" in msg
    assert "us-east-1" in msg
    assert "https://gateway.us-east-1.wp2.wasp.silvios.me" in msg
    assert "https://gateway.sa-east-1.wp2.wasp.silvios.me" in msg


async def test_telegram_notifier_send_posts_message(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import wasp.clients.telegram.notifier as n

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
    from tests.notifiers import RecordingNotifier

    n = RecordingNotifier()
    await n.send("123", "hello")
    await n.send("456", "world")

    assert n.messages == [
        {"chat_id": "123", "text": "hello"},
        {"chat_id": "456", "text": "world"},
    ]


async def test_recording_notifier_wait_for_message_resolves_after_send():
    import asyncio
    from tests.notifiers import RecordingNotifier

    n = RecordingNotifier()

    async def _send_after_delay():
        await asyncio.sleep(0.05)
        await n.send("1", "msg")

    asyncio.create_task(_send_after_delay())
    await asyncio.wait_for(n.wait_for_message(), timeout=2)
    assert len(n.messages) == 1


async def test_watch_platform_notifies_when_ready(monkeypatch):
    from unittest.mock import MagicMock
    import wasp.watcher as w
    from tests.notifiers import RecordingNotifier

    api = MagicMock()
    api.get_cluster_custom_object.return_value = {
        "spec": {
            "regions": [
                {
                    "name": "us-east-1",
                    "endpoint": "gateway.us-east-1.wp2.wasp.silvios.me",
                }
            ]
        },
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    notifier = RecordingNotifier()

    await w.watch_platform("wp2", "12345", notifier)

    assert len(notifier.messages) == 1
    assert notifier.messages[0]["chat_id"] == "12345"
    assert "wp2" in notifier.messages[0]["text"]
    assert (
        "https://gateway.us-east-1.wp2.wasp.silvios.me" in notifier.messages[0]["text"]
    )


async def test_watch_platform_retries_on_404_until_timeout(monkeypatch):
    from itertools import chain, repeat
    from unittest.mock import AsyncMock, MagicMock
    import wasp.watcher as w
    from tests.notifiers import RecordingNotifier

    class FakeApiException(Exception):
        def __init__(self, status, reason):
            self.status = status
            self.reason = reason

    monkeypatch.setattr(w, "ApiException", FakeApiException)

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = FakeApiException(
        status=404, reason="NotFound"
    )
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
    import wasp.watcher as w
    from tests.notifiers import RecordingNotifier

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
    from wasp.watcher import _find_condition

    assert (
        _find_condition(
            {"status": {"conditions": [{"type": "Synced", "status": "True"}]}}, "Ready"
        )
        is None
    )
    assert _find_condition({}, "Ready") is None


async def test_watch_platform_reraises_non_404_exception(monkeypatch):
    from unittest.mock import MagicMock
    import wasp.watcher as w
    from tests.notifiers import RecordingNotifier

    class FakeApiException(Exception):
        def __init__(self, status, reason):
            self.status = status
            self.reason = reason

    monkeypatch.setattr(w, "ApiException", FakeApiException)

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = FakeApiException(
        status=500, reason="InternalServerError"
    )
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)

    # Non-404 exceptions are caught, logged, and do not propagate from watch_platform
    await w.watch_platform("wp2", "12345", RecordingNotifier())


async def test_watcher_records_polls_counter(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from tests.notifiers import RecordingNotifier
    import wasp.telemetry as telemetry

    reader = InMemoryMetricReader()
    telemetry.configure(metric_reader=reader)

    import wasp.watcher as w

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
    from tests.notifiers import RecordingNotifier
    import wasp.telemetry as telemetry

    reader = InMemoryMetricReader()
    telemetry.configure(metric_reader=reader)

    import wasp.watcher as w

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
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from opentelemetry.trace import SpanContext, TraceFlags
    from tests.notifiers import RecordingNotifier
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    import wasp.watcher as w

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
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from tests.notifiers import RecordingNotifier
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    import wasp.watcher as w

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
    import wasp.watcher as w
    from tests.notifiers import RecordingNotifier

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


def test_extract_chat_id_from_local_session():
    from wasp.watcher import extract_chat_id

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    assert extract_chat_id(FakeCtx()) == "abc12345"


def test_extract_chat_id_from_local_session_with_suffix():
    from wasp.watcher import extract_chat_id

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345:8ec68b0f"

    assert extract_chat_id(FakeCtx()) == "abc12345"


async def test_console_notifier_logs_message(caplog):
    import logging
    from wasp.clients.local import ConsoleNotifier

    caplog.set_level(logging.INFO, logger="wasp.clients.local.notifier")
    notifier = ConsoleNotifier()
    await notifier.send("abc123", "Plataforma test está pronta.")

    assert any(
        "[NOTIFIER chat_id=abc123]" in r.message
        and "Plataforma test está pronta." in r.message
        for r in caplog.records
    )


def test_select_notifier_console_when_env_explicit(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.clients.local import ConsoleNotifier

    monkeypatch.setenv("AGENT_NOTIFIER", "console")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_telegram_when_env_explicit(monkeypatch):
    import wasp.clients.telegram  # noqa: F401
    from wasp.watcher import _select_notifier
    from wasp.clients.telegram import TelegramNotifier

    monkeypatch.setenv("AGENT_NOTIFIER", "tg")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_default_telegram_when_token(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.clients.telegram import TelegramNotifier

    monkeypatch.delenv("AGENT_NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_default_console_without_token(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.clients.local import ConsoleNotifier

    monkeypatch.delenv("AGENT_NOTIFIER", raising=False)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    notifier = _select_notifier()
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_returns_none_when_telegram_without_token(monkeypatch):
    import wasp.clients.telegram  # noqa: F401
    from wasp.watcher import _select_notifier

    monkeypatch.setenv("AGENT_NOTIFIER", "tg")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    assert _select_notifier() is None


def test_select_notifier_returns_none_for_unknown_kind(monkeypatch):
    from wasp.watcher import _select_notifier

    monkeypatch.setenv("AGENT_NOTIFIER", "unknown_kind")
    assert _select_notifier() is None


def test_select_notifier_local_channel_picks_console_even_with_telegram_token(
    monkeypatch,
):
    from wasp.watcher import _select_notifier
    from wasp.clients.local import ConsoleNotifier

    monkeypatch.delenv("AGENT_NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier(channel="local")
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_tg_channel_picks_telegram(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.clients.telegram import TelegramNotifier

    monkeypatch.delenv("AGENT_NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier(channel="tg")
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_env_overrides_channel(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.clients.local import ConsoleNotifier

    monkeypatch.setenv("AGENT_NOTIFIER", "console")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier(channel="tg")
    assert isinstance(notifier, ConsoleNotifier)


def test_spawner_no_chat_id_returns_false(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    thread_cls = MagicMock()
    with patch("wasp.watcher.threading.Thread", thread_cls):
        result = PlatformWatcherSpawner().spawn(
            name="x", chat_id=None, channel="tg", parent_span_ctx=None
        )

    assert result is False
    thread_cls.assert_not_called()


def test_spawner_no_notifier_returns_false(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    monkeypatch.setenv("AGENT_NOTIFIER", "telegram")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    thread_cls = MagicMock()
    with patch("wasp.watcher.threading.Thread", thread_cls):
        result = PlatformWatcherSpawner().spawn(
            name="x", chat_id="111", channel="tg", parent_span_ctx=None
        )

    assert result is False
    thread_cls.assert_not_called()


def test_spawner_spawns_thread(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    monkeypatch.setenv("AGENT_NOTIFIER", "console")
    thread = MagicMock()
    thread_cls = MagicMock(return_value=thread)
    with patch("wasp.watcher.threading.Thread", thread_cls):
        result = PlatformWatcherSpawner().spawn(
            name="x", chat_id="111", channel="local", parent_span_ctx=None
        )

    assert result is True
    thread_cls.assert_called_once()
    thread.start.assert_called_once()


def test_spawner_target_runs_asyncio(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    monkeypatch.setenv("AGENT_NOTIFIER", "console")

    thread = MagicMock()
    thread_cls = MagicMock(return_value=thread)
    mock_watch = MagicMock()
    mock_async_run = MagicMock()

    with (
        patch("wasp.watcher.threading.Thread", thread_cls),
        patch("wasp.watcher.asyncio.run", mock_async_run),
        patch("wasp.watcher.watch_platform", mock_watch),
    ):
        PlatformWatcherSpawner().spawn(
            name="x", chat_id="111", channel="local", parent_span_ctx=None
        )
        target = thread_cls.call_args.kwargs["target"]
        target()

    mock_async_run.assert_called_once_with(mock_watch.return_value)


def test_select_notifier_dc_channel_uses_registered_channel(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.clients import channels
    from wasp.watcher import _select_notifier

    fake_notifier = MagicMock()
    fake_channel = MagicMock()
    fake_channel.name = "dc"
    fake_channel.notifier = MagicMock(return_value=fake_notifier)
    channels.register(fake_channel)

    monkeypatch.delenv("AGENT_NOTIFIER", raising=False)
    assert _select_notifier(channel="dc") is fake_notifier


def test_select_notifier_dc_channel_returns_none_when_unregistered(monkeypatch):
    from wasp.watcher import _select_notifier

    monkeypatch.delenv("AGENT_NOTIFIER", raising=False)
    assert _select_notifier(channel="dc") is None


def test_select_notifier_env_kind_resolves_via_registry(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.clients import channels
    from wasp.watcher import _select_notifier

    fake_notifier = MagicMock()
    fake_channel = MagicMock()
    fake_channel.name = "dc"
    fake_channel.notifier = MagicMock(return_value=fake_notifier)
    channels.register(fake_channel)

    monkeypatch.setenv("AGENT_NOTIFIER", "dc")
    assert _select_notifier() is fake_notifier


def test_extract_channel_returns_dc_for_discord_session():
    from wasp.watcher import extract_channel

    class FakeCtx:
        session_id = "dc:wasp-agent:123456789"

    assert extract_channel(FakeCtx()) == "dc"


def test_extract_chat_id_returns_user_id_for_discord_session():
    from wasp.watcher import extract_chat_id

    class FakeCtx:
        session_id = "dc:wasp-agent:123456789"

    assert extract_chat_id(FakeCtx()) == "123456789"


def test_platform_spawner_registers_watch_before_threading():
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    call_order = []
    mock_repo = MagicMock()
    mock_repo.register.side_effect = lambda *a, **kw: call_order.append("register")
    mock_thread_cls = MagicMock(
        side_effect=lambda *a, **kw: call_order.append("thread") or MagicMock()
    )

    with (
        patch("wasp.watcher.threading.Thread", mock_thread_cls),
        patch("wasp.watcher._select_notifier", return_value=MagicMock()),
        patch("wasp.watcher.get_watch_repository", return_value=mock_repo),
    ):
        result = PlatformWatcherSpawner().spawn(
            name="p1",
            chat_id="12345",
            channel="tg",
            parent_span_ctx=None,
            session_id="tg:agent:12345",
        )

    assert result is True
    assert call_order == ["register", "thread"]
    mock_repo.register.assert_called_once_with("Platform", "p1", "tg:agent:12345")


def test_cluster_spawner_registers_watch_before_threading():
    from unittest.mock import MagicMock, patch
    from wasp.watcher import ClusterWatcherSpawner

    call_order = []
    mock_repo = MagicMock()
    mock_repo.register.side_effect = lambda *a, **kw: call_order.append("register")
    mock_thread_cls = MagicMock(
        side_effect=lambda *a, **kw: call_order.append("thread") or MagicMock()
    )

    with (
        patch("wasp.watcher.threading.Thread", mock_thread_cls),
        patch("wasp.watcher._select_notifier", return_value=MagicMock()),
        patch("wasp.watcher.get_watch_repository", return_value=mock_repo),
    ):
        result = ClusterWatcherSpawner().spawn(
            name="c1",
            chat_id="42",
            channel="dc",
            parent_span_ctx=None,
            session_id="dc:agent:42",
        )

    assert result is True
    assert call_order == ["register", "thread"]
    mock_repo.register.assert_called_once_with("Cluster", "c1", "dc:agent:42")


def test_spawner_skips_register_when_no_session_id():
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    mock_repo = MagicMock()

    with (
        patch("wasp.watcher.threading.Thread", MagicMock()),
        patch("wasp.watcher._select_notifier", return_value=MagicMock()),
        patch("wasp.watcher.get_watch_repository", return_value=mock_repo),
    ):
        PlatformWatcherSpawner().spawn("p1", "123", "tg", None, session_id=None)

    mock_repo.register.assert_not_called()


async def test_watch_cluster_inner_raises_on_non_404_apiexception(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import wasp.watcher as w
    from tests.notifiers import RecordingNotifier

    class FakeApiException(Exception):
        def __init__(self, status, reason=""):
            self.status = status
            self.reason = reason

    monkeypatch.setattr(w, "ApiException", FakeApiException)

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = FakeApiException(
        status=500, reason="InternalServerError"
    )
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)

    import pytest

    with pytest.raises(FakeApiException):
        await w._watch_cluster_inner("c1", "12345", RecordingNotifier())

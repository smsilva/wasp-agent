import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


def test_configure_noop_by_default(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    import wasp.telemetry as telemetry

    telemetry.configure()
    assert telemetry.tracer is not None
    assert telemetry.meter is not None


def test_configure_with_in_memory_exporters():
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    telemetry.configure(span_exporter=exporter, metric_reader=reader)
    assert telemetry.tracer is not None
    assert telemetry.meter is not None


def test_instrument_sync_records_span():
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    @telemetry.instrument("test.op")
    def my_fn(x):
        return x * 2

    result = my_fn(3)
    assert result == 6

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test.op"


def test_instrument_sync_records_error_status():
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    @telemetry.instrument("test.fail")
    def broken():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        broken()

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    from opentelemetry.trace import StatusCode

    assert spans[0].status.status_code == StatusCode.ERROR


@pytest.mark.asyncio
async def test_instrument_async_records_span():
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    @telemetry.instrument("test.async")
    async def async_fn():
        return "done"

    result = await async_fn()
    assert result == "done"

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test.async"


def test_instrument_records_tool_call_counter():
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    telemetry.configure(span_exporter=exporter, metric_reader=reader)

    @telemetry.instrument("my.tool")
    def my_tool():
        return "ok"

    my_tool()
    metrics_data = reader.get_metrics_data()
    metric_names = {
        m.name
        for rm in metrics_data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert "agent.tool_calls.total" in metric_names


def test_instrument_records_duration_histogram():
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    telemetry.configure(span_exporter=exporter, metric_reader=reader)

    @telemetry.instrument("my.tool")
    def my_tool():
        return "ok"

    my_tool()
    metrics_data = reader.get_metrics_data()
    metric_names = {
        m.name
        for rm in metrics_data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert "agent.tool_calls.duration_seconds" in metric_names


def test_configure_with_otlp_endpoint(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
        MagicMock(),
    )
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter",
        MagicMock(),
    )
    with patch("openinference.instrumentation.agno.AgnoInstrumentor", MagicMock()):
        import wasp.telemetry as telemetry

        telemetry.configure()
    assert telemetry.tracer is not None
    assert telemetry.meter is not None


def test_configure_instruments_agno_when_endpoint_set(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
        MagicMock(),
    )
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter",
        MagicMock(),
    )
    mock_instrumentor = MagicMock()
    mock_instrumentor_cls = MagicMock(return_value=mock_instrumentor)
    with patch(
        "openinference.instrumentation.agno.AgnoInstrumentor", mock_instrumentor_cls
    ):
        import wasp.telemetry as telemetry  # noqa: F401

    mock_instrumentor.instrument.assert_called_once()
    call_kwargs = mock_instrumentor.instrument.call_args.kwargs
    assert "tracer_provider" in call_kwargs
    from openinference.instrumentation import TraceConfig

    config = call_kwargs["config"]
    assert isinstance(config, TraceConfig)
    assert config.hide_inputs is True
    assert config.hide_outputs is True


def test_configure_skips_agno_without_endpoint(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    mock_instrumentor = MagicMock()
    mock_instrumentor_cls = MagicMock(return_value=mock_instrumentor)
    with patch(
        "openinference.instrumentation.agno.AgnoInstrumentor", mock_instrumentor_cls
    ):
        import wasp.telemetry as telemetry  # noqa: F401

    mock_instrumentor.instrument.assert_not_called()


def test_configure_agno_hide_io_false(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("OTEL_AGNO_HIDE_IO", "false")
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
        MagicMock(),
    )
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter",
        MagicMock(),
    )
    mock_instrumentor = MagicMock()
    mock_instrumentor_cls = MagicMock(return_value=mock_instrumentor)
    with patch(
        "openinference.instrumentation.agno.AgnoInstrumentor", mock_instrumentor_cls
    ):
        import wasp.telemetry as telemetry  # noqa: F401

    from openinference.instrumentation import TraceConfig

    config = mock_instrumentor.instrument.call_args.kwargs["config"]
    assert isinstance(config, TraceConfig)
    assert config.hide_inputs is False
    assert config.hide_outputs is False


def test_watcher_metrics_exist_after_configure():
    import wasp.telemetry as telemetry

    reader = InMemoryMetricReader()
    telemetry.configure(metric_reader=reader)
    assert telemetry.provisioning_counter is not None
    assert telemetry.watcher_duration is not None
    assert telemetry.watcher_polls_counter is not None


def test_configure_default_has_no_prometheus_registry(monkeypatch):
    monkeypatch.delenv("PROMETHEUS_METRICS_ACTIVE", raising=False)
    import wasp.telemetry as telemetry

    telemetry.configure()
    assert telemetry._prometheus_registry is None


def test_configure_with_prometheus_port_creates_registry(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_METRICS_ACTIVE", "9999")
    import wasp.telemetry as telemetry

    telemetry.configure()
    assert telemetry._prometheus_registry is not None


def test_prometheus_output_includes_tool_calls_metric(monkeypatch):
    from prometheus_client import generate_latest

    monkeypatch.setenv("PROMETHEUS_METRICS_ACTIVE", "9999")
    import wasp.telemetry as telemetry

    telemetry.configure()

    @telemetry.instrument("my.probe")
    def probe():
        return "ok"

    probe()

    output = generate_latest(telemetry._prometheus_registry).decode()
    assert "agent_tool_calls_total" in output


def test_configure_with_explicit_reader_skips_prometheus_registry():
    import wasp.telemetry as telemetry

    reader = InMemoryMetricReader()
    telemetry.configure(metric_reader=reader)
    assert telemetry._prometheus_registry is None


@pytest.mark.asyncio
async def test_instrument_async_records_error_status():
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    @telemetry.instrument("test.async.fail")
    async def broken():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await broken()

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    from opentelemetry.trace import StatusCode

    assert spans[0].status.status_code == StatusCode.ERROR

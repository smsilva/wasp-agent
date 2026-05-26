import functools
import inspect
import os
import time

from opentelemetry import metrics as _metrics_api, trace as _trace_api
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import StatusCode
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY as _PROM_REGISTRY,
    Counter as _PromCounter,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

tracer: _trace_api.Tracer = None  # type: ignore[assignment]
meter: _metrics_api.Meter = None  # type: ignore[assignment]

_tool_calls_counter = None
_tool_calls_duration = None

provisioning_counter = None
watcher_duration = None
watcher_polls_counter = None

_prometheus_registry = None


def configure(*, span_exporter=None, metric_reader=None) -> None:
    global \
        tracer, \
        meter, \
        _tool_calls_counter, \
        _tool_calls_duration, \
        _prometheus_registry

    service_name = os.getenv("OTEL_SERVICE_NAME", "wasp-agent")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    # Tracer provider
    tp = TracerProvider()
    if span_exporter is not None:
        tp.add_span_processor(SimpleSpanProcessor(span_exporter))
    elif endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    _trace_api.set_tracer_provider(tp)
    tracer = tp.get_tracer(service_name)

    if endpoint:
        from openinference.instrumentation import TraceConfig
        from openinference.instrumentation.agno import AgnoInstrumentor

        hide = os.getenv("OTEL_AGNO_HIDE_IO", "true").lower() != "false"
        AgnoInstrumentor().instrument(
            tracer_provider=tp,
            config=TraceConfig(hide_inputs=hide, hide_outputs=hide),
        )

    # Meter provider
    readers = []
    if metric_reader is not None:
        _prometheus_registry = None
        readers.append(metric_reader)
    else:
        if os.getenv("PROMETHEUS_METRICS_ACTIVE"):
            import prometheus_client as _prom
            from opentelemetry.exporter.prometheus import PrometheusMetricReader

            _prometheus_registry = _prom.REGISTRY
            readers.append(PrometheusMetricReader())
        else:
            _prometheus_registry = None
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

            readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
    mp = MeterProvider(metric_readers=readers)
    _metrics_api.set_meter_provider(mp)
    meter = mp.get_meter(service_name)

    _tool_calls_counter = meter.create_counter(
        "agent.tool_calls.total",
        description="Tool invocations",
    )
    _tool_calls_duration = meter.create_histogram(
        "agent.tool_calls.duration_seconds",
        description="Tool call latency",
        unit="s",
    )

    global provisioning_counter, watcher_duration, watcher_polls_counter
    provisioning_counter = meter.create_counter(
        "agent.provisioning.total",
        description="Provisioning lifecycle events",
    )
    watcher_duration = meter.create_histogram(
        "agent.watcher.duration_seconds",
        description="Watcher spawn-to-notification time",
        unit="s",
    )
    watcher_polls_counter = meter.create_counter(
        "agent.watcher.polls.total",
        description="Individual watcher poll iterations",
    )

    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    LoggingInstrumentor().instrument(set_logging_format=False)


configure()


# Module-level Counter — defined once. Uses prometheus_client directly
# (not OTel meter) so the metric is always emitted on the Prometheus scrape
# regardless of OTel exporter configuration.
_AUTH_DENIED_METRIC_NAME = "wasp_auth_denied_total"
if _AUTH_DENIED_METRIC_NAME in _PROM_REGISTRY._names_to_collectors:
    _auth_denied_counter = _PROM_REGISTRY._names_to_collectors[_AUTH_DENIED_METRIC_NAME]
else:
    _auth_denied_counter = _PromCounter(
        _AUTH_DENIED_METRIC_NAME,
        "Total auth denial events",
        ["channel", "reason"],
    )


def auth_denied(*, channel: str, reason: str) -> None:
    """Increments wasp_auth_denied_total{channel,reason}."""
    _auth_denied_counter.labels(channel=channel, reason=reason).inc()


def instrument(name: str):
    """Decorator: span + agent.tool_calls.* metrics. Works on sync and async functions."""

    def decorator(fn):
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                with tracer.start_as_current_span(name) as span:
                    status = "ok"
                    try:
                        return await fn(*args, **kwargs)
                    except Exception as exc:
                        status = "error"
                        span.set_status(StatusCode.ERROR, str(exc))
                        raise
                    finally:
                        elapsed = time.perf_counter() - t0
                        _tool_calls_counter.add(1, {"tool": name, "status": status})
                        _tool_calls_duration.record(elapsed, {"tool": name})

            return async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                with tracer.start_as_current_span(name) as span:
                    status = "ok"
                    try:
                        return fn(*args, **kwargs)
                    except Exception as exc:
                        status = "error"
                        span.set_status(StatusCode.ERROR, str(exc))
                        raise
                    finally:
                        elapsed = time.perf_counter() - t0
                        _tool_calls_counter.add(1, {"tool": name, "status": status})
                        _tool_calls_duration.record(elapsed, {"tool": name})

            return sync_wrapper

    return decorator


async def metrics_endpoint(request: Request) -> Response:
    data = (
        generate_latest(_prometheus_registry)
        if _prometheus_registry is not None
        else generate_latest()
    )
    return Response(data, media_type=CONTENT_TYPE_LATEST)


def register_prometheus_route(app) -> None:
    app.routes.append(Route("/telemetry/prometheus", metrics_endpoint))

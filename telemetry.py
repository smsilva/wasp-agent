import asyncio
import functools
import os
import time

from opentelemetry import metrics as _metrics_api, trace as _trace_api
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import StatusCode

tracer: _trace_api.Tracer = None  # type: ignore[assignment]
meter: _metrics_api.Meter = None  # type: ignore[assignment]

_tool_calls_counter = None
_tool_calls_duration = None


def configure(*, span_exporter=None, metric_reader=None) -> None:
    global tracer, meter, _tool_calls_counter, _tool_calls_duration

    service_name = os.getenv("OTEL_SERVICE_NAME", "wasp-agent")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    # Tracer provider
    tp = TracerProvider()
    if span_exporter is not None:
        tp.add_span_processor(SimpleSpanProcessor(span_exporter))
    elif endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        tp.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
    _trace_api.set_tracer_provider(tp)
    tracer = tp.get_tracer(service_name)

    # Meter provider
    readers = []
    if metric_reader is not None:
        readers.append(metric_reader)
    elif endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
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


configure()


def instrument(name: str):
    """Decorator: span + agent.tool_calls.* metrics. Works on sync and async functions."""
    def decorator(fn):
        if asyncio.iscoroutinefunction(fn):
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

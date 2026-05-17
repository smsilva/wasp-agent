# OpenTelemetry Instrumentation — Design Spec

**Date:** 2026-05-17  
**Status:** Approved

## Goal

Instrument wasp-agent with OpenTelemetry to understand how the agent is used
over time. Telemetry serves two purposes: real-time monitoring and building a
baseline dataset that a future AI agent can analyze for troubleshooting and
improvement opportunities.

## Approach

Manual OTel SDK instrumentation using the built-in `@tracer.start_as_current_span`
decorator and a thin custom `@instrument` decorator that combines span lifecycle
with metric recording. All signal providers (tracer, meter, logger) are initialized
once in `telemetry.py` and used as module-level globals.

Configuration is 100% via OTel-standard env vars. When
`OTEL_EXPORTER_OTLP_ENDPOINT` is not set, all providers fall back to no-op
exporters — no telemetry, no overhead, no errors.

## Architecture

```
main.py  ──import──►  telemetry.py  (init providers at startup)
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         TracerProvider  MeterProvider  LoggerProvider
              │            │            │
         OTLP exporter  OTLP exporter  OTLP exporter
              │            │
          (New Relic)   Prometheus reader
                           │
                       GET /metrics  (Starlette route added in main.py)
```

`telemetry.py` exposes: `tracer`, `meter`, `logger` (globals), `instrument`
(decorator), and `configure(*, exporter_override=None)` (used in tests to inject
`InMemorySpanExporter` / `InMemoryMetricReader`).

## Configuration

| Env var | Default | Description |
|---|---|---|
| `OTEL_SERVICE_NAME` | `wasp-agent` | Service name in the backend |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (empty) | If absent → no-op mode |
| `OTEL_EXPORTER_OTLP_HEADERS` | (empty) | e.g. `api-key=<NEW_RELIC_KEY>` |
| `PROMETHEUS_PORT` | `9464` | Port for `/metrics` scraping endpoint |

For New Relic free tier:
```
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.nr-data.net:4318
OTEL_EXPORTER_OTLP_HEADERS=api-key=<NR_LICENSE_KEY>
```

When running in Kubernetes, any OTLP-compatible backend can receive data by
changing these env vars — no code changes required.

## Signals

### Metrics

| Metric | Type | Labels | What it measures |
|---|---|---|---|
| `agent.messages.total` | Counter | `channel`, `user_id` | Messages received per channel |
| `agent.tool_calls.total` | Counter | `tool`, `status` (`ok`/`error`), `channel` | Tool invocations |
| `agent.tool_calls.duration_seconds` | Histogram | `tool` | Tool call latency |
| `agent.provisioning.total` | Counter | `outcome` (`started`/`ready`/`timeout`/`error`) | Provisioning lifecycle |
| `agent.watcher.duration_seconds` | Histogram | `outcome` (`ready`/`timeout`) | Spawn-to-notification time |
| `agent.watcher.polls.total` | Counter | `result` (`pending`/`not_found`/`ready`) | Individual watcher polls |

`channel` values follow the `session_id` prefix convention (`tg`, `discord`,
`slack`, etc.) — derived from the same parsing logic as `extract_chat_id`.

### Traces

**Span: `agent.tool.execute`** — root span per tool invocation.
Attributes: `tool.name`, `platform.name`, `channel`, `user_id`, `session_id`.
`channel` and `user_id` are derived from `run_context.session_id` at call time.

Note: messages that result in pure text responses (no tool call) are not traced
in this version — agno provides no pre-routing hook that exposes session context.
This is an accepted gap for the initial implementation.

- **Child `agent.github.commit`** — GitHub file creation.
  Attributes: `commit.sha`, `repo`.
- **Child `agent.watcher.spawn`** — records the spawn event.
  Attribute: `watcher.spawned=true`. Closed immediately (does not wait).

**Span: `agent.watcher.lifecycle`** — *separate trace*, linked to the
`agent.tool.execute` span above via `SpanLink`. Covers the full polling cycle
from spawn to Ready notification or timeout.
Attributes: `platform.name`, `outcome`, `poll_count`, `duration_seconds`.

Rationale for separate trace: the watcher runs in a daemon thread with its own
event loop that may outlive the HTTP request by up to 10 minutes. The parent
`SpanContext` is captured at spawn time and passed to the watcher as a
`SpanLink` — standard OTel pattern for async fire-and-forget work.

### Logs (structured)

Consolidates with the pending `2026-05-16-structured-logging.md` spec. Same
JSONL format. When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, logs are also
forwarded via `OTLPLogExporter`. Fields: `timestamp`, `level`, `message`, plus
`trace_id` and `span_id` when emitted within an active span.

## Decorator pattern

The OTel SDK provides a built-in decorator:
```python
@tracer.start_as_current_span("span_name")
def some_function(): ...
```

For `@tool` functions, decorator order matters — `@tool` must be the outermost
decorator so agno receives the tool-annotated callable. `@tracer.start_as_current_span`
is applied as the inner decorator; `functools.wraps` preserves `__doc__`,
`__annotations__`, and `__wrapped__` so `inspect.signature()` (used by agno for
schema generation) resolves to the original function:

```python
@tool                                                 # outer — seen by agno
@tracer.start_as_current_span("agent.tool.execute")  # inner — span lifecycle
def provision_platform_instance(...):
    ...
    trace.get_current_span().set_attribute("platform.name", name)
```

For metrics (counters + histograms), a thin custom `@instrument` decorator in
`telemetry.py` combines span and metric recording in one decorator. The
argument is the `tool` label used in `agent.tool_calls.*` metrics and also the
span name:

```python
@tool
@instrument("provision_platform_instance")       # span name + metric label
def provision_platform_instance(...):
    ...

@instrument("watcher.lifecycle")                 # works on sync and async functions
async def _watch_platform_inner(...):
    ...
```

`@instrument` detects `asyncio.iscoroutinefunction` at decoration time and
wraps accordingly. Runtime-derived attributes (`platform.name`, `outcome`) are
set via `trace.get_current_span().set_attribute(...)` inside the function body.

## Integration with agno

agno has no native OTel hooks. Instrumentation points:

1. **Tool calls** — `@instrument("provision_platform_instance")` on the tool
   function. `channel` and `user_id` populated from `run_context.session_id`.
2. **GitHub commit** — `with tracer.start_as_current_span("agent.github.commit")`
   context manager inside `provision_platform_instance`.
3. **Watcher spawn** — span attribute `watcher.spawned=true` set on the current
   span; `SpanContext` captured via `trace.get_current_span().get_span_context()`
   and passed to `watch_platform`.
4. **Watcher lifecycle** — `@instrument("watcher.lifecycle")` on
   `_watch_platform_inner`; starts a new root span with a `SpanLink` to the
   parent tool span context.
5. **Poll metrics** — `agent.watcher.polls.total` counter incremented on each
   poll iteration inside `_watch_platform_inner`.
6. **Duration metric** — `agent.watcher.duration_seconds` histogram recorded on
   watcher exit (Ready or timeout), labeled with `outcome`.

## New files and changes

| File | Change |
|---|---|
| `telemetry.py` | New — providers, `instrument` decorator, `configure()` |
| `main.py` | Import `telemetry`, add `/metrics` route |
| `tools/provision.py` | Add `@instrument`, span attributes, watcher context propagation |
| `tools/watcher.py` | Add `@instrument` on `_watch_platform_inner`, poll/duration metrics |
| `tests/test_telemetry.py` | New — unit tests for `telemetry.py` (no-op mode, instrument decorator) |
| `tests/test_provision.py` | Update — assert telemetry calls via in-memory exporters |
| `tests/test_watcher.py` | Update — assert watcher metrics via in-memory reader |
| `pyproject.toml` | Add OTel dependencies |

## Dependencies to add

```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
opentelemetry-exporter-prometheus
opentelemetry-instrumentation-logging
```

## Testing strategy

`telemetry.configure(exporter_override=...)` accepts an `InMemorySpanExporter`
and `InMemoryMetricReader` for test injection. Tests assert span names,
attributes, and metric values without requiring a live backend. 100% coverage
maintained.

No-op mode (no `OTEL_EXPORTER_OTLP_ENDPOINT`) is the default in tests —
telemetry does not affect test outcomes unless explicitly configured.

## Out of scope

- Auto-instrumentation via `opentelemetry-distro` (too noisy)
- Baggage propagation across services
- Sampling configuration (defer to OTel defaults)
- Dashboard templates for New Relic / Grafana

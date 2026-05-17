# OpenTelemetry Instrumentation — Cycle 4 Implementation Plan

**Goal:** Instrumentar wasp-agent com OpenTelemetry conforme o spec [`docs/specs/2026-05-17-opentelemetry-design.md`](../specs/2026-05-17-opentelemetry-design.md). Traces, métricas e structured logs. No-op quando `OTEL_EXPORTER_OTLP_ENDPOINT` não está definido.

**Approach:** TDD strict (red-green-refactor). Cobertura 100% verificada com `pytest --cov`. Cada Task termina com `ruff check .` limpo e commit conventional.

---

### Task 1: Add OTel dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Adicionar dependências em `[project].dependencies`**

```toml
"opentelemetry-api>=1.25.0",
"opentelemetry-sdk>=1.25.0",
"opentelemetry-exporter-otlp-proto-http>=1.25.0",
"opentelemetry-exporter-prometheus>=0.46b0",
"opentelemetry-instrumentation-logging>=0.46b0",
```

- [ ] **Step 2: `uv sync`**

```bash
uv sync
```

- [ ] **Step 3: Verificar imports**

```bash
python -c "
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.exporter.prometheus import PrometheusMetricReader
print('ok')
"
```

Esperado: `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add opentelemetry packages for Cycle 4"
```

---

### Task 2: `telemetry.py` (TDD)

**Files:**
- Create: `tests/test_telemetry.py`
- Create: `telemetry.py`

OTel SDK é instalado como dependência real — não é mockado no conftest. Testes usam `InMemorySpanExporter` e `InMemoryMetricReader` para asserções sem backend.

- [ ] **Step 1: Testes falhando — `tests/test_telemetry.py`**

```python
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


def test_configure_noop_by_default(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    import telemetry
    telemetry.configure()
    assert telemetry.tracer is not None
    assert telemetry.meter is not None


def test_configure_with_in_memory_exporters():
    import telemetry
    exporter = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    telemetry.configure(span_exporter=exporter, metric_reader=reader)
    assert telemetry.tracer is not None
    assert telemetry.meter is not None


def test_instrument_sync_records_span():
    import telemetry
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
    import telemetry
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
    import telemetry
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
    import telemetry
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
    import telemetry
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
```

```bash
pytest tests/test_telemetry.py -v
```

Esperado: 7 FAIL (módulo `telemetry` não existe).

- [ ] **Step 2: Criar `telemetry.py`**

```python
import asyncio
import functools
import os
import time

from opentelemetry import metrics as _metrics_api, trace as _trace_api
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
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
```

```bash
pytest tests/test_telemetry.py -v
```

Esperado: 7 PASS.

- [ ] **Step 3: Coverage**

```bash
pytest tests/test_telemetry.py --cov=telemetry --cov-report=term-missing
```

Esperado: 100% em `telemetry.py`.

- [ ] **Step 4: Ruff**

```bash
ruff check .
```

- [ ] **Step 5: Commit**

```bash
git add telemetry.py tests/test_telemetry.py
git commit -m "feat(telemetry): add OTel providers and instrument decorator"
```

---

### Task 3: Métricas do watcher em `telemetry.py`

As métricas do watcher (`agent.watcher.*` e `agent.provisioning.total`) são criadas em `telemetry.py` como globals acessíveis pelos módulos de tool. Adicionar ao `configure()` e expor como módulo-nível.

**Files:**
- Modify: `telemetry.py`
- Modify: `tests/test_telemetry.py`

- [ ] **Step 1: Testes falhando**

Append em `tests/test_telemetry.py`:

```python
def test_watcher_metrics_exist_after_configure():
    import telemetry
    reader = InMemoryMetricReader()
    telemetry.configure(metric_reader=reader)
    assert telemetry.provisioning_counter is not None
    assert telemetry.watcher_duration is not None
    assert telemetry.watcher_polls_counter is not None
```

```bash
pytest tests/test_telemetry.py::test_watcher_metrics_exist_after_configure -v
```

Esperado: 1 FAIL.

- [ ] **Step 2: Adicionar globals em `telemetry.py`**

Após `_tool_calls_duration = ...` em `configure()`, adicionar:

```python
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
```

Declarar os globals no topo do módulo (junto com `tracer`, `meter`):

```python
provisioning_counter = None
watcher_duration = None
watcher_polls_counter = None
```

```bash
pytest tests/test_telemetry.py -v
```

Esperado: 8 PASS.

- [ ] **Step 3: Coverage + Ruff + Commit**

```bash
pytest tests/test_telemetry.py --cov=telemetry --cov-report=term-missing
ruff check .
git add telemetry.py tests/test_telemetry.py
git commit -m "feat(telemetry): add provisioning and watcher metric globals"
```

---

### Task 4: Atualizar `conftest.py`

`telemetry` e `tools.provision` precisam ser recarregados a cada teste para que `configure()` seja executado com a fixture certa.

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Adicionar `telemetry` ao cleanup de módulos**

Em `conftest.py`, adicionar `"telemetry"` ao conjunto de módulos limpos no `mock_agno`:

```python
for mod in ("main", "tools", "tools.provision", "tools.watcher", "telemetry"):
    sys.modules.pop(mod, None)
```

(Tanto no `yield` pré quanto no pós.)

- [ ] **Step 2: Rodar suite completa para validar sem quebrar nada**

```bash
pytest -v
```

Esperado: todos PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(conftest): reset telemetry module between tests"
```

---

### Task 5: Instrumentar `tools/provision.py`

**Files:**
- Modify: `tools/provision.py`
- Modify: `tests/test_provision.py`

- [ ] **Step 1: Testes falhando — span e métricas de provisioning**

Append em `tests/test_provision.py`:

```python
def test_provision_creates_span(monkeypatch):
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    import telemetry
    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    from unittest.mock import MagicMock
    mock_github_cls = MagicMock()
    mock_repo = MagicMock()
    mock_github_cls.return_value.get_repo.return_value = mock_repo

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setattr("tools.provision.Github", mock_github_cls)
    monkeypatch.setattr("tools.provision.threading.Thread", MagicMock())

    from tools.provision import provision_platform_instance
    provision_platform_instance(name="wp-test")

    spans = exporter.get_finished_spans()
    assert any(s.name == "provision_platform_instance" for s in spans)


def test_provision_records_provisioning_started(monkeypatch):
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    import telemetry
    reader = InMemoryMetricReader()
    telemetry.configure(metric_reader=reader)

    from unittest.mock import MagicMock
    mock_github_cls = MagicMock()
    mock_repo = MagicMock()
    mock_github_cls.return_value.get_repo.return_value = mock_repo

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setattr("tools.provision.Github", mock_github_cls)
    monkeypatch.setattr("tools.provision.threading.Thread", MagicMock())

    from tools.provision import provision_platform_instance
    provision_platform_instance(name="wp-test")

    metrics_data = reader.get_metrics_data()
    all_points = [
        dp
        for rm in metrics_data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "agent.provisioning.total"
        for dp in m.data.data_points
    ]
    assert any(dp.attributes.get("outcome") == "started" for dp in all_points)
```

```bash
pytest tests/test_provision.py::test_provision_creates_span tests/test_provision.py::test_provision_records_provisioning_started -v
```

Esperado: 2 FAIL.

- [ ] **Step 2: Modificar `tools/provision.py`**

Adicionar import no topo:

```python
import telemetry
from opentelemetry import trace
```

Envolver `provision_platform_instance` com `@instrument`:

```python
@tool
@telemetry.instrument("provision_platform_instance")
def provision_platform_instance(
    name: str,
    domain: str = DEFAULT_DOMAIN,
    regions: list[str] | None = None,
    requested_by: str = "",
    run_context=None,
) -> dict:
```

Dentro da função, após `repo.create_file(...)` bem-sucedido, adicionar atributos e métricas:

```python
        current_span = trace.get_current_span()
        current_span.set_attribute("platform.name", name)

        # Capturar contexto pai para o watcher
        parent_span_ctx = current_span.get_span_context()

        telemetry.provisioning_counter.add(1, {"outcome": "started"})

        chat_id = extract_chat_id(run_context)
        token = os.getenv("TELEGRAM_TOKEN")
        if chat_id and token:
            current_span.set_attribute("watcher.spawned", True)
            threading.Thread(
                target=asyncio.run,
                args=(watch_platform(name, chat_id, token, parent_span_ctx),),
                daemon=True,
            ).start()
```

E na branch de erro (`except Exception`), adicionar:

```python
        telemetry.provisioning_counter.add(1, {"outcome": "error"})
```

- [ ] **Step 3: Todos os testes de provision passam**

```bash
pytest tests/test_provision.py -v
```

Esperado: todos PASS.

- [ ] **Step 4: Coverage + Ruff + Commit**

```bash
pytest tests/test_provision.py --cov=tools.provision --cov-report=term-missing
ruff check .
git add tools/provision.py tests/test_provision.py
git commit -m "feat(provision): instrument with OTel span and provisioning counter"
```

---

### Task 6: Instrumentar `tools/watcher.py`

**Files:**
- Modify: `tools/watcher.py`
- Modify: `tests/test_watcher.py`

O watcher roda em thread separada com event loop próprio. O span `agent.watcher.lifecycle` é uma **trace separada** vinculada ao span do tool via `SpanLink`.

- [ ] **Step 1: Atualizar assinatura de `watch_platform` para aceitar `parent_span_ctx`**

Em `tools/watcher.py`, modificar:

```python
async def watch_platform(name: str, chat_id: str, token: str, parent_span_ctx=None) -> None:
    log.info("Watcher started for %s", name)
    try:
        await _watch_platform_inner(name, chat_id, token, parent_span_ctx)
    except Exception:
        log.exception("Watcher failed for %s", name)
```

E `_watch_platform_inner`:

```python
async def _watch_platform_inner(
    name: str, chat_id: str, token: str, parent_span_ctx=None
) -> None:
```

- [ ] **Step 2: Testes falhando — métricas do watcher**

Append em `tests/test_watcher.py`:

```python
@pytest.mark.asyncio
async def test_watcher_records_polls_counter(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
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
    monkeypatch.setattr(w, "notify_telegram", AsyncMock())

    await w.watch_platform("wp1", "123", "tok")

    metrics_data = reader.get_metrics_data()
    metric_names = {
        m.name
        for rm in metrics_data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert "agent.watcher.polls.total" in metric_names


@pytest.mark.asyncio
async def test_watcher_records_duration_on_ready(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
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
    monkeypatch.setattr(w, "notify_telegram", AsyncMock())

    await w.watch_platform("wp1", "123", "tok")

    metrics_data = reader.get_metrics_data()
    metric_names = {
        m.name
        for rm in metrics_data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert "agent.watcher.duration_seconds" in metric_names


@pytest.mark.asyncio
async def test_watcher_creates_lifecycle_span(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
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
    monkeypatch.setattr(w, "notify_telegram", AsyncMock())

    await w.watch_platform("wp1", "123", "tok")

    spans = exporter.get_finished_spans()
    assert any(s.name == "agent.watcher.lifecycle" for s in spans)
```

```bash
pytest tests/test_watcher.py::test_watcher_records_polls_counter tests/test_watcher.py::test_watcher_records_duration_on_ready tests/test_watcher.py::test_watcher_creates_lifecycle_span -v
```

Esperado: 3 FAIL.

- [ ] **Step 3: Modificar `tools/watcher.py`**

Adicionar imports:

```python
import time
import telemetry
from opentelemetry import trace
from opentelemetry.trace import Link, NonRecordingSpan, SpanContext, TraceFlags
```

Substituir `_watch_platform_inner` com lógica de telemetria:

```python
async def _watch_platform_inner(
    name: str, chat_id: str, token: str, parent_span_ctx=None
) -> None:
    links = []
    if parent_span_ctx and parent_span_ctx.is_valid:
        links = [Link(parent_span_ctx)]

    with telemetry.tracer.start_as_current_span(
        "agent.watcher.lifecycle", links=links
    ) as span:
        span.set_attribute("platform.name", name)
        api = load_kube_config_auto()
        deadline = time.monotonic() + WATCH_TIMEOUT_SECONDS
        t0 = time.perf_counter()
        poll_count = 0

        while time.monotonic() < deadline:
            try:
                platform = api.get_cluster_custom_object(
                    group=PLATFORM_GROUP,
                    version=PLATFORM_VERSION,
                    plural=PLATFORM_PLURAL,
                    name=name,
                )
            except ApiException as e:
                if e.status == 404:
                    poll_count += 1
                    telemetry.watcher_polls_counter.add(1, {"result": "not_found"})
                    log.debug("Platform %s not in cluster yet, sleeping %ss", name, POLL_INTERVAL_SECONDS)
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue
                raise

            poll_count += 1
            condition = _find_condition(platform, "Ready")
            if condition and condition.get("status") == "True":
                telemetry.watcher_polls_counter.add(1, {"result": "ready"})
                elapsed = time.perf_counter() - t0
                telemetry.watcher_duration.record(elapsed, {"outcome": "ready"})
                span.set_attribute("outcome", "ready")
                span.set_attribute("poll_count", poll_count)
                span.set_attribute("duration_seconds", elapsed)
                log.info("Platform %s is Ready — notifying", name)
                await notify_telegram(chat_id, token, ready_message(name, platform))
                return

            telemetry.watcher_polls_counter.add(1, {"result": "pending"})
            log.debug("Platform %s not ready yet, sleeping %ss", name, POLL_INTERVAL_SECONDS)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        elapsed = time.perf_counter() - t0
        telemetry.watcher_duration.record(elapsed, {"outcome": "timeout"})
        span.set_attribute("outcome", "timeout")
        span.set_attribute("poll_count", poll_count)
        span.set_attribute("duration_seconds", elapsed)
        log.warning("Watcher timeout for %s", name)
        await notify_telegram(
            chat_id,
            token,
            f"Provisionamento de '{name}' ainda em andamento após 10 minutos. Verifique mais tarde.",
        )
```

```bash
pytest tests/test_watcher.py -v
```

Esperado: todos PASS.

- [ ] **Step 4: Coverage + Ruff + Commit**

```bash
pytest tests/test_watcher.py --cov=tools.watcher --cov-report=term-missing
ruff check .
git add tools/watcher.py tests/test_watcher.py
git commit -m "feat(watcher): instrument lifecycle span and poll/duration metrics"
```

---

### Task 7: Atualizar `main.py` — rota `/metrics` e import de telemetry

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Verificar como `test_main.py` está estruturado atualmente**

```bash
cat tests/test_main.py
```

Entender quais testes existem e o que precisam ser atualizados.

- [ ] **Step 2: Testes falhando — rota `/metrics` existe**

Append em `tests/test_main.py`:

```python
def test_metrics_route_exists():
    import main
    routes = [r.path for r in main.app.routes if hasattr(r, "path")]
    assert "/metrics" in routes
```

```bash
pytest tests/test_main.py::test_metrics_route_exists -v
```

Esperado: 1 FAIL.

- [ ] **Step 3: Modificar `main.py`**

Após `load_dotenv()` e antes dos imports do agno, adicionar:

```python
import telemetry  # noqa: E402 — must come after load_dotenv so env vars are set
```

Após `app = agent_os.get_app()`, adicionar:

```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import Response  # noqa: E402
from starlette.routing import Route  # noqa: E402


async def metrics_endpoint(request: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.routes.append(Route("/metrics", metrics_endpoint))
```

- [ ] **Step 4: Todos os testes passam**

```bash
pytest -v
```

Esperado: todos PASS.

- [ ] **Step 5: Coverage total**

```bash
pytest --cov --cov-report=term-missing
```

Esperado: 100% em `main.py`, `telemetry.py`, `tools/provision.py`, `tools/watcher.py`.

Se alguma linha não coberta, adicionar teste mínimo para cobri-la.

- [ ] **Step 6: Ruff**

```bash
ruff check .
```

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat(main): import telemetry and add /metrics route"
```

---

### Task 8: Merge `dev` → `main`

- [ ] **Step 1: Confirmar tudo limpo em `dev`**

```bash
pytest --cov --cov-report=term-missing
ruff check .
git status
```

- [ ] **Step 2: PR**

```bash
gh pr create \
  --base main \
  --head dev \
  --title "feat: Cycle 4 — OpenTelemetry instrumentation" \
  --body "..."
```

- [ ] **Step 3: Merge**

```bash
gh pr merge --squash
```

- [ ] **Step 4: Arquivar spec e plano**

```bash
git mv docs/specs/2026-05-17-opentelemetry-design.md docs/specs/archived/
git mv docs/plans/2026-05-17-opentelemetry-cycle4.md docs/plans/archived/
```

Atualizar `**Status:**` do spec para `Implemented` antes de mover.

- [ ] **Step 5: Atualizar HANDOFF.md**

Marcar Ciclo 4 como completo.

---

## Notes

- `telemetry.configure()` é chamado automaticamente no import com no-op providers. Testes que precisam de asserções OTel chamam `telemetry.configure(span_exporter=..., metric_reader=...)` após importar o módulo. Não há necessidade de mockar OTel no conftest — SDK é instalado como dependência real.
- `agent.messages.total` foi omitido desta implementação: agno não expõe hook pré-roteamento que forneça `session_id` antes de decidir se há tool call. Documentar como limitação aceita no spec.
- A rota `/metrics` usa `prometheus_client.generate_latest()`. O `PrometheusMetricReader` registra automaticamente no registry default do `prometheus_client`, então a rota serve os dados sem configuração adicional.
- Se `main.py` importar `telemetry` no nível de módulo, o `conftest.py` precisa que `main` seja limpo do `sys.modules` (já feito). Os testes de `main` que precisarem de spans/métricas injetarão via `telemetry.configure(...)` antes de importar `main`.

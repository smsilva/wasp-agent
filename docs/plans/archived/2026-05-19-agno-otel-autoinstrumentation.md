# Plano: Ciclo 5 — `openinference-instrumentation-agno`

**Date:** 2026-05-19  
**Spec:** `docs/specs/2026-05-17-agno-otel-autoinstrumentation.md`

## Objetivo

Integrar `openinference-instrumentation-agno` ao `telemetry.py` para ganhar spans de LLM (latência, tokens), AGENT (run id, session id) e TOOL automaticamente, conectados na mesma trace dos spans domain-specific do Ciclo 4.

## Tasks

### Task 1 — Adicionar dependência

```
uv add openinference-instrumentation-agno
```

Verificar: `uv run python -c "from openinference.instrumentation.agno import AgnoInstrumentor"` sem erro.

### Task 2 — Migrar para `BatchSpanProcessor` em `telemetry.py`

**Onde:** bloco `elif endpoint:` em `configure()` (linha ~34).

Trocar:
```python
tp.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
```
Por:
```python
from opentelemetry.sdk.trace.export import BatchSpanProcessor
tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
```

`SimpleSpanProcessor` permanece apenas no caminho `if span_exporter is not None:` (usado em testes com `InMemorySpanExporter`).

### Task 3 — Ativar `AgnoInstrumentor` em `configure()`

No final do bloco `if endpoint:` (após criar `BatchSpanProcessor`), adicionar:

```python
from openinference.instrumentation.agno import AgnoInstrumentor
from openinference.instrumentation import TraceConfig
hide = os.getenv("OTEL_AGNO_HIDE_IO", "true").lower() != "false"
AgnoInstrumentor().instrument(
    tracer_provider=tp,
    config=TraceConfig(hide_inputs=hide, hide_outputs=hide),
)
```

Condição: só quando `endpoint` está presente — sem endpoint, sem AgnoInstrumentor (evita monkey-patching desnecessário em dev/teste).

### Task 4 — Testes

Novos testes em `test_telemetry.py`:

1. **`test_configure_instruments_agno_when_endpoint_set`** — patch `AgnoInstrumentor` e `BatchSpanProcessor`; assert `instrument()` chamado com `tracer_provider=tp` e `config` com `hide_inputs=True, hide_outputs=True`.
2. **`test_configure_skips_agno_without_endpoint`** — sem `OTEL_EXPORTER_OTLP_ENDPOINT`; assert `AgnoInstrumentor().instrument` **não** chamado.
3. **`test_configure_agno_hide_io_false`** — `OTEL_AGNO_HIDE_IO=false`; assert `TraceConfig(hide_inputs=False, hide_outputs=False)`.

Cobertura 100% obrigatória. `ruff check .` clean.

### Task 5 — Atualizar spec e HANDOFF

- `docs/specs/2026-05-17-agno-otel-autoinstrumentation.md` → `Status: Implemented` (no merge para `main`)
- `HANDOFF.md` → remover item 2 dos Next Steps; adicionar smoke test do endpoint OTLP ao item 3

## Verificação final

```bash
uv run pytest -W error::DeprecationWarning --cov
uv run ruff check .
```

Ambos devem passar limpos.
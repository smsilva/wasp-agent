# Avaliar `openinference-instrumentation-agno` como complemento ao Ciclo 4

**Date:** 2026-05-17  
**Status:** Approved  
**Scope:** Observabilidade do agente — auto-instrumentação OTel via biblioteca oficial agno.

## Problema

O Ciclo 4 (`docs/specs/2026-05-17-opentelemetry-design.md`) adicionou spans e métricas **domain-specific** (`provision_platform_instance`, `agent.watcher.lifecycle`, provisioning counter, watcher duration). Isso cobre a parte de provisionamento e watcher, mas **não captura**:

- Chamadas ao LLM (Bedrock/Claude) — latência, tokens, custo
- Decisões do agente (qual tool foi escolhida, com que argumentos)
- Conversation flow (run id, session id, mensagens)

agno tem suporte a OTel via `openinference-instrumentation-agno` (auto-instrumentação mantida pela Arize). A documentação lista backends como Arize Phoenix, Langfuse, Logfire, OpenLIT, etc. Ativando essa instrumentação, ganhamos esses spans **sem código adicional**.

## Investigação concluída

### 1. Relação com `agno.setup_tracing()` / `tracing=True`

São mecanismos **distintos e independentes**:

- `tracing=True` / `setup_tracing()` — tracing first-party do agno, armazena spans numa `TracesTable` (SQLite/PostgreSQL) e expõe via Control Plane UI. Não envia para OTLP.
- `openinference-instrumentation-agno` — auto-instrumentor third-party (Arize), usa `wrapt` para monkey-patching de `_run`, `_arun`, `_run_stream` e `Model.invoke*`. Emite spans para o OTLP backend configurado. Não escreve em banco.

Podem coexistir sem conflito. Se ambos ativos com um OTLP backend, a trace tree de agno aparece duplicada no backend externo — evitar ativar `tracing=True` se já usando openinference.

### 2. Spans e atributos emitidos por default

**AGENT span** (um por `agent.run()`):
- `openinference.span.kind = "AGENT"`
- `input.value` — mensagem do usuário (texto completo)
- `output.value` — resposta do agente (JSON completo)
- `session.id`, `user.id`, `agno.run.id` (UUID)
- `agent.name`, `agno.agent.id`

**LLM span** (um por chamada ao modelo):
- `openinference.span.kind = "LLM"`
- `llm.model_name`, `llm.provider`
- `llm.input_messages.N.message.{role,content}` — **prompt completo**
- `llm.output_messages.N.message.{role,content}` — **resposta completa**
- `llm.token_count.{prompt,completion,total}`, cache read/write
- `llm.invocation_parameters` (model params; API keys filtrados para `[REDACTED]`)

**TOOL span** (um por tool call):
- `openinference.span.kind = "TOOL"`
- `tool.name`, `tool.description`, `tool.parameters`
- `input.value` (JSON dos argumentos), `output.value` (resultado da tool)

Também instrumenta `Workflow`, `Step`, `Parallel` quando presentes.

**Bugs conhecidos:**
- Token counts nem sempre emitidos corretamente ([#3951](https://github.com/agno-agi/agno/issues/3951))
- Context detach error em async streaming ([#5208](https://github.com/agno-agi/agno/issues/5208)) — capturado internamente, gera log noise
- Nested traces erradas em sequential team runs ([#5573](https://github.com/agno-agi/agno/issues/5573))

### 3. TracerProvider compartilhado

`AgnoInstrumentor().instrument()` aceita `tracer_provider` explicitamente:

```python
AgnoInstrumentor().instrument(tracer_provider=tp)
```

Se não passado, usa `trace_api.get_tracer_provider()` (o global). Como `telemetry.py` já chama `_trace_api.set_tracer_provider(tp)`, basta chamar `AgnoInstrumentor().instrument()` após `configure()` — sem criar segundo TracerProvider.

### 4. Privacidade — prompts capturados

**Sim, por default.** `llm.input_messages` inclui o system prompt completo + mensagens do usuário. `input.value` no AGENT span contém a mensagem Telegram do usuário.

Riscos concretos neste projeto:
- Mensagens Telegram de usuários → atributo `input.value` no OTLP backend
- System prompt com instruções sensíveis → `llm.input_messages`
- Argumentos da tool `provision_platform_instance` → `input.value` no TOOL span (contém `name`, `domain`, `regions` — aceitável)

**Redacting via `TraceConfig`:**

```python
from openinference.instrumentation import TraceConfig
config = TraceConfig(hide_inputs=True, hide_outputs=True)
AgnoInstrumentor().instrument(tracer_provider=tp, config=config)
```

Valores ocultados são substituídos por `"__REDACTED__"`. Configurável via env vars:
- `OPENINFERENCE_HIDE_INPUTS=true`
- `OPENINFERENCE_HIDE_OUTPUTS=true`

**Decisão: redaction ativa por default.** Manter `hide_inputs=True, hide_outputs=True` no código. Para debug em dev, desativar via env vars sem alterar código.

### 5. Custo em performance

- **Startup**: `find_model_subclasses()` percorre `agno.models` via `pkgutil.walk_packages` — ocorre uma vez no `instrument()`, não no hot path.
- **Por-request**: `start_span` + serialização de mensagens com `safe_json_dumps` por LLM call. Overhead típico de OTel — desprezível vs. latência do LLM.
- **Exporter**: `SimpleSpanProcessor` (usado atualmente em `telemetry.py`) é síncrono e **bloqueia** o thread. Para produção, usar `BatchSpanProcessor`.

## Decisão

**Adotar**, com as seguintes condições:

1. `TraceConfig(hide_inputs=True, hide_outputs=True)` ativo por default
2. Migrar `SimpleSpanProcessor` → `BatchSpanProcessor` no `telemetry.py` para o exporter OTLP (o `SimpleSpanProcessor` para testes permanece, pois é controlado)
3. Ativar apenas quando `OTEL_EXPORTER_OTLP_ENDPOINT` estiver configurado (mesma lógica já usada para spans domain-specific)
4. Não ativar `tracing=True` no agno para evitar duplicação

## Design

### Mudanças em `telemetry.py`

```python
from opentelemetry.sdk.trace.export import BatchSpanProcessor  # troca SimpleSpanProcessor no elif endpoint:

# No final de configure(), após _trace_api.set_tracer_provider(tp):
if endpoint:
    from openinference.instrumentation.agno import AgnoInstrumentor
    from openinference.instrumentation import TraceConfig
    hide = os.getenv("OTEL_AGNO_HIDE_IO", "true").lower() != "false"
    AgnoInstrumentor().instrument(
        tracer_provider=tp,
        config=TraceConfig(hide_inputs=hide, hide_outputs=hide),
    )
```

### Nova dependência

```
openinference-instrumentation-agno
```

### Testes

- `test_telemetry.py`: assert que `AgnoInstrumentor().instrument` é chamado quando `OTEL_EXPORTER_OTLP_ENDPOINT` está setado; não chamado quando endpoint vazio.
- Cobertura 100% mantida.

### Env vars novas

| Var | Default | Efeito |
|---|---|---|
| `OTEL_AGNO_HIDE_IO` | `"true"` | `"false"` re-expõe prompts/respostas no OTLP backend (só para debug) |

## Saídas esperadas

- `telemetry.py` atualizado (BatchSpanProcessor + AgnoInstrumentor)
- Testes atualizados (cobertura 100%)
- Env var `OTEL_AGNO_HIDE_IO` documentada no runbook de observabilidade

## Referências

- [openinference-instrumentation-agno PyPI](https://pypi.org/project/openinference-instrumentation-agno/)
- [Arize-ai/openinference GitHub](https://github.com/Arize-ai/openinference)
- [OpenInference configuration spec](https://arize-ai.github.io/openinference/spec/configuration.html)
- [agno tracing docs](https://docs.agno.com/tracing/overview)
- `docs/specs/2026-05-17-opentelemetry-design.md` (Ciclo 4 — implementado)
# OpenTelemetry — Distributed Tracing

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

O `wasp-agent` já tem métricas Prometheus e logs estruturados. O terceiro pilar de observabilidade — **traces** — está ausente. Em uma requisição ao webhook, múltiplas camadas executam em sequência: HTTP → auth → LLM → tool call → GitOps commit → resposta. Métricas dizem "p95 = 3s"; logs dizem "cada evento separado". Só traces dizem "nesta requisição específica, o LLM levou 2.8s e o commit GitOps levou 0.1s".

O projeto já tem `OTEL_EXPORTER_OTLP_ENDPOINT` como variável de ambiente — a infraestrutura de exportação está prevista, mas a instrumentação não está especificada.

## Os três pilares — distinções

| Pilar | Pergunta | Granularidade |
|---|---|---|
| **Métricas** | Qual é a saúde agregada do sistema? | Agregado (p95, rate, count) |
| **Logs** | O que aconteceu em um evento específico? | Evento individual |
| **Traces** | Quanto tempo cada parte levou nesta requisição? | Causalidade entre operações |

Traces são especialmente valiosos em agentes LLM porque o fluxo tem latências heterogêneas e não-lineares (LLM pode chamar múltiplas tools em sequência ou paralelo).

## Conceitos OpenTelemetry

**Trace:** representação de uma requisição do início ao fim. Tem um `trace_id` único.

**Span:** unidade de trabalho dentro de um trace. Tem `span_id`, `parent_span_id`, timestamps de início/fim, e atributos. Spans formam uma árvore.

**Context propagation:** `trace_id` e `span_id` são propagados entre serviços via headers HTTP (W3C TraceContext: `traceparent`).

**OTLP:** protocolo padrão de exportação de telemetria (OpenTelemetry Protocol). Suporta gRPC e HTTP/protobuf.

## Instrumentação no wasp-agent

### Spans esperados por requisição

```
POST /telegram/webhook [root span]
  ├── parse_telegram_payload
  ├── is_authorized [auth span]
  ├── llm_call [LLM span]
  │     ├── tool: provision_platform_instance
  │     │     ├── k8s_apply_manifest
  │     │     └── gitops_commit
  │     └── tool: list_platform_instances
  │           └── k8s_list_resources
  └── send_notification [notifier span]
```

### Atributos de span recomendados

Para spans LLM (seguir [OpenTelemetry Semantic Conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)):

```python
span.set_attribute("gen_ai.system", "anthropic")
span.set_attribute("gen_ai.request.model", model_name)
span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
span.set_attribute("gen_ai.response.finish_reason", finish_reason)
span.set_attribute("wasp.prompt_version", PROMPT_VERSION)
span.set_attribute("wasp.chat_id", chat_id)
span.set_attribute("wasp.channel", channel)
```

### Instrumentação automática vs. manual

**Automática (zero-code):**
- `opentelemetry-instrumentation-fastapi` — instrumenta todos os endpoints HTTP automaticamente.
- `opentelemetry-instrumentation-httpx` — instrumenta chamadas HTTP de saída (Anthropic API, GitHub API).
- `opentelemetry-instrumentation-sqlite3` — instrumenta queries SQLite.

**Manual (spans de negócio):**
```python
from opentelemetry import trace

tracer = trace.get_tracer("wasp-agent")

async def provision_platform_instance(name: str) -> dict:
    with tracer.start_as_current_span("provision_platform_instance") as span:
        span.set_attribute("wasp.platform.name", name)
        ...
```

Recomendação: instrumentação automática para infraestrutura + manual para operações de negócio (tool calls, decisões LLM).

## Backends de trace

| Backend | Modo | Quando usar |
|---|---|---|
| **Jaeger** (self-hosted) | Docker Compose local | Desenvolvimento local |
| **Tempo** (Grafana) | Self-hosted ou Grafana Cloud | Se já usa Grafana para métricas |
| **Honeycomb** (SaaS) | Free tier generoso | Sem infra própria, quer UI boa |
| **OTLP stdout** | Sem backend | Debug local sem dependência |

Para `make e2e`: exportar para stdout (`OTEL_TRACES_EXPORTER=console`) — zero dependência de infra.
Para produção: Jaeger em Docker Compose ou Tempo no cluster.

## Configuração

```python
# wasp/telemetry.py (extensão do existente)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def configure_tracing(app: FastAPI) -> None:
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return  # tracing opcional; não quebra se não configurado

    provider = TracerProvider(resource=Resource({
        SERVICE_NAME: "wasp-agent",
        SERVICE_VERSION: __version__,
    }))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
```

Tracing deve ser **opt-in via env var** — não quebrar o agente quando backend não está disponível.

## Correlação com logs e métricas

Injetar `trace_id` e `span_id` nos logs estruturados:

```python
span = trace.get_current_span()
ctx = span.get_span_context()
logger.info("llm_call", extra={
    "trace_id": format(ctx.trace_id, "032x"),
    "span_id": format(ctx.span_id, "016x"),
    ...
})
```

Permite navegar de uma linha de log para o trace completo no Jaeger/Tempo.

## Conexão com outros specs

- **Observabilidade (checklist):** fecha o gap do terceiro pilar — métricas + logs + traces.
- **Load testing (`2026-05-26-load-testing.md`):** traces durante teste de carga revelam gargalos específicos (qual tool call domina a latência).
- **Incident Response (`2026-05-26-incident-response.md`):** nos primeiros 5 minutos de um incidente, traces são a ferramenta de diagnóstico mais eficaz.
- **Prompt Versioning (`2026-05-26-prompt-versioning.md`):** `prompt_version` como atributo de span permite correlacionar latência LLM com versão de prompt.
- **DORA Metrics (`2026-05-26-dora-metrics.md`):** traces fornecem dado granular para MTTR — quanto do tempo de recuperação foi em cada camada.

## Armadilhas

- **Tracing síncrono bloqueando a requisição.** Usar `BatchSpanProcessor`, não `SimpleSpanProcessor` — o batch envia assincronamente sem adicionar latência ao path crítico.
- **Atributos com dados pessoais.** Não adicionar `message.text` (conteúdo da mensagem do usuário) como atributo de span — dado pessoal em telemetria vira problema de privacidade.
- **Sampling agressivo em desenvolvimento.** Sem sampling, 100% das requisições geram traces — OK para desenvolvimento, caro em produção. Configurar `OTEL_TRACES_SAMPLER=parentbased_traceidratio` com taxa < 1.0 em prod.
- **Backend indisponível quebrando o agente.** Tracing deve degradar graciosamente — se o exporter falhar, a requisição deve continuar normalmente.

## Fora de escopo desta nota

- Distributed tracing entre múltiplos serviços (agente + cluster + ArgoCD) — requer propagação de contexto via headers K8s.
- Profiling contínuo (Pyroscope, Parca) — categoria diferente de observabilidade.
- Log aggregation (Loki, ELK) — complementar mas spec separado.

## Próximo passo

Promover a Draft quando o agente for containerizado. Ação imediata: adicionar `opentelemetry-instrumentation-fastapi` e exportar para stdout (`OTEL_TRACES_EXPORTER=console`) em desenvolvimento — zero backend, zero custo, traces visíveis no terminal.

## Referências

- [OpenTelemetry Python](https://opentelemetry-python.readthedocs.io/)
- [OTel Semantic Conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Jaeger](https://www.jaegertracing.io/)
- [Grafana Tempo](https://grafana.com/oss/tempo/)
- [Honeycomb](https://www.honeycomb.io/)
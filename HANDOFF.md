# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–5 completos e em `main`.

## Current Progress

**Ciclos 1–5 em `main`.** Smoke test end-to-end do Ciclo 4 validado em 2026-05-17 (Telegram → GitHub → ArgoCD → Crossplane → watcher → notificação proativa). Ciclo 5 validado em 2026-05-19 com `make smoke` (spans AGENT + LLM chegando ao Jaeger).

### Esta sessão (2026-05-19)

- **Fix `RuntimeWarning`** (`90327d9`): coroutine de `watch_platform` criada dentro de `_run_watcher` (closure) — só criada quando a thread executa, não na hora do provisionamento.
- **Ciclo 5 — `openinference-instrumentation-agno`** (`afb0f73`):
  - `BatchSpanProcessor` substituiu `SimpleSpanProcessor` no path OTLP (não bloqueia thread)
  - `AgnoInstrumentor().instrument(tracer_provider=tp, config=TraceConfig(...))` ativado quando `OTEL_EXPORTER_OTLP_ENDPOINT` presente
  - `OTEL_AGNO_HIDE_IO=false` re-expõe prompts para debug local (default: redactado)
  - 3 novos testes, cobertura 100%, ruff clean
- **Smoke test + infra** (`87fa5f2`): `docker-compose.yml` (Jaeger), `make smoke`, `smoke_agno_otel.py`
- **Specs/plans arquivados**: Ciclos 4 e 5 movidos para `archived/`
- **`/telemetry/prometheus` validado** (`smoke_prometheus.py` + `make smoke-prometheus`):
  - `PrometheusMetricReader` adicionado a `telemetry.configure()` quando `PROMETHEUS_PORT` está definido
  - `metrics_endpoint` passa `telemetry._prometheus_registry` para `generate_latest()`
  - Smoke script verifica `agent_tool_calls_total`, `agent_provisioning_total`, `agent_watcher_polls_total`, `agent_watcher_duration_seconds`
  - 49 testes, 100% cobertura, ruff clean

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/sdlc/02-design/2026-05-16-structured-logging.md` | Deferred (avaliar consolidação com OTel logs) |

### Plans ativos

Nenhum.

## What Worked

- **TDD via subagent** para Ciclos 4 e 5: cobertura 100% mantida desde o início, ruff clean a cada commit.
- **`SpanLink`** para correlacionar trabalho assíncrono do watcher ao span síncrono da tool — padrão OTel correto para fire-and-forget.
- **`pytest -W error::DeprecationWarning` sem filtros adicionais** — confirma fixes sem mascarar nada.
- **`make smoke` + Jaeger** — validação E2E de spans sem precisar de infraestrutura permanente.

## What Didn't Work

- **Rota `/metrics`**: agno reserva esse path. Movido para `/telemetry/prometheus`.
- **Default logging WARNING** escondeu logs do watcher na primeira execução do smoke test.
- **Suposição errada sobre `session_id`**: agno 2.0+ adiciona suffix de message hash (4 partes, não 3).
- **Tentativa de suprimir DeprecationWarning** com `-W ignore` — hábito perigoso. Persistido em `feedback-no-suppressing-warnings.md`.

## Next Steps

### Brainstorms abertos

- `docs/sdlc/01-exploration/2026-05-17-e2e-testing-without-external-chats.md` — pipeline E2E em cluster efêmero (k3d/vcluster), gitops mock, Telegram mock, validação de métricas. Próximo: decidir cluster + gitops mock, depois virar spec.

### Backlog

- **Structured logging completo** (`docs/sdlc/02-design/2026-05-16-structured-logging.md`) — JSONL via `LOG_FILE`, `OTLPLogExporter` integration. Avaliar consolidação com OTel logs do Ciclo 5.
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`) — persistir `platform_watches` em SQLite para sobreviver a restarts.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
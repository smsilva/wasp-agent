# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–3 completos em `main`. **Ciclo 4 (OpenTelemetry)** implementado, validado E2E e estabilizado em `dev`. Pronto pro merge — usuário vai conduzir.

## Current Progress

**Ciclos 1, 2 e 3 em `main`.** Smoke test end-to-end do Ciclo 4 validado em 2026-05-17 (Telegram → GitHub → ArgoCD → Crossplane → watcher → notificação proativa).

### Esta sessão (2026-05-17)

- **Plano OTel Ciclo 4 criado** (`4c4020c`) e implementado via subagent (Tasks 1–7), TDD estrito, cobertura 100%, ruff clean.
  - `telemetry.py` (providers + `@instrument` decorator)
  - Metric globals: provisioning_counter, watcher_duration, watcher_polls_counter
  - `provision.py` instrumentado (span + counter); `watcher.py` com `agent.watcher.lifecycle` linkado via `Link(parent_span_ctx)` ao span da tool
  - `main.py` expõe Prometheus endpoint (path final `/telemetry/prometheus` — ver fix abaixo)
- **Quick fix de logging** (`24ce281`): `logging.basicConfig(level=LOG_LEVEL)` em `main.py`. Destravou diagnóstico.
- **Bug crítico do `chat_id`** (`dc381fe`): agno 2.0+ usa `session_id = tg:<agent>:<chat_id>:<message_short_id>` (4 partes). `extract_chat_id` pegava `parts[-1]` (o hash) → `notify_telegram` recebia chat_id inválido → HTTP 400 silencioso. Corrigido para `parts[2]`, dois testes cobrindo ambos os formatos.
- **Smoke test E2E validado**: provisionou `wp-smoke2` via Telegram, watcher detectou Ready e enviou notificação. Cleanup feito no gitops repo (`cb9c15e` em wasp-gitops).
- **Fix `/metrics` shadow** (`f2f199a`): agno reserva `/metrics` e `/metrics/refresh` pro dashboard REST. Movido nosso Prometheus para `/telemetry/prometheus`.
- **Fix `DeprecationWarning`** (`940a4ac`): `asyncio.iscoroutinefunction` → `inspect.iscoroutinefunction` em `telemetry.py:83`. Validado com `pytest -W error::DeprecationWarning` (40 testes passam, zero warnings de deprecation).
- **Novo spec idea** (`098e2a5`): `docs/specs/2026-05-17-agno-otel-autoinstrumentation.md` — avaliar `openinference-instrumentation-agno` para ganhar spans de LLM/agent run conectados na mesma trace dos spans de domínio.
- **Learnings persistidos**:
  - `docs/references/agno.md` (`94eadfe`): formato do `session_id` com suffix opcional + reserva de `/metrics` e `/metrics/refresh`.
  - Memória pessoal: `feedback-no-suppressing-warnings.md` — nunca usar `-W ignore::<Warning>` sem antes investigar.

### Commits no `dev` ainda não em `main`

```
90327d9 fix(provision): defer coroutine creation to _run_watcher closure
94eadfe docs(agno): note session_id format and /metrics reservation
940a4ac fix(telemetry): use inspect.iscoroutinefunction (asyncio variant deprecated)
098e2a5 docs(specs): add idea to evaluate openinference-instrumentation-agno
f2f199a fix(main): move Prometheus endpoint to /telemetry/prometheus
dc381fe fix(watcher): extract chat_id from parts[2], not parts[-1]
24ce281 feat(main): configure root logger to surface app INFO logs
c2d710c feat(main): import telemetry and add /metrics route
8945a7a feat(watcher): instrument lifecycle span and poll/duration metrics
2e2cca8 feat(provision): instrument with OTel span and provisioning counter
fe9ea4c test(conftest): reset telemetry module between tests
9e03ed6 feat(telemetry): add provisioning and watcher metric globals
25c1863 feat(telemetry): add OTel providers and instrument decorator
9c0207c chore(deps): add opentelemetry packages for Cycle 4
4c4020c docs(plans): add OTel cycle 4 implementation plan and update HANDOFF
+ commits anteriores de reorganização docs (452ca56, 39f0870, 42592ab, 045cc0b, e530d61)
```

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/specs/2026-05-17-opentelemetry-design.md` | Approved (implementado, arquivar no merge) |
| `docs/specs/2026-05-17-agno-otel-autoinstrumentation.md` | Draft (investigação concluída; aguarda aprovação para planejar implementação) |
| `docs/specs/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/specs/2026-05-16-structured-logging.md` | Deferred (será consolidado com OTel) |

### Plans ativos

| Arquivo | Status |
|---|---|
| `docs/plans/2026-05-17-opentelemetry-cycle4.md` | Tasks 1–7 done; Task 8 (merge) deixada com o usuário |

## What Worked

- **TDD via subagent** para Tasks 1–7: cobertura 100% mantida desde o início, ruff clean a cada commit.
- **`SpanLink`** (não `set_attribute("parent_span_ctx", ...)`) para correlacionar trabalho assíncrono do watcher ao span síncrono da tool — padrão OTel correto para fire-and-forget.
- **Logging via env var** (`LOG_LEVEL`) como quick fix antes do spec completo de structured logging — destravou diagnóstico em minutos.
- **`pytest -W error::DeprecationWarning` sem filtros adicionais** — confirma que o fix realmente eliminou o warning sem mascarar nada.

## What Didn't Work

- **Rota `/metrics`**: agno reserva esse path pra dashboard REST. `app.routes.append(...)` foi silenciosamente sombreado. Corrigido pra `/telemetry/prometheus` em `f2f199a`.
- **Default logging WARNING** escondeu logs do watcher na primeira execução do smoke test — investigação cega até adicionar `basicConfig`.
- **Suposição errada sobre `session_id`**: assumi 3 partes baseado em código histórico; agno 2.0+ adiciona suffix de message hash. Lição: `peek` no `agent.db` antes de confiar no formato.
- **Tentativa de suprimir warning de teste** com `-W ignore::DeprecationWarning:unittest.mock` — usuário cobrou. Filtro era inútil mas o hábito é perigoso (pode mascarar DeprecationWarning real). Persistido em `feedback-no-suppressing-warnings.md`.

## Next Steps

1. **Task 8: Merge `dev` → `main`** — usuário vai conduzir. Depois arquivar `docs/specs/2026-05-17-opentelemetry-design.md` e `docs/plans/2026-05-17-opentelemetry-cycle4.md` em `archived/` (per CLAUDE.md §7).
2. **Aprovar spec draft** — `docs/specs/2026-05-17-agno-otel-autoinstrumentation.md`. Investigação concluída: adotar com `hide_inputs/outputs=True` por default, `BatchSpanProcessor`, ativar só quando `OTEL_EXPORTER_OTLP_ENDPOINT` presente. Aguarda sinal verde do usuário para criar plano de implementação.
3. **Smoke test do endpoint `/telemetry/prometheus`** — não validado E2E ainda. Após o merge:
   - Subir o agente, provisionar uma Platform via Telegram (ou ngrok local)
   - `curl http://localhost:7777/telemetry/prometheus` durante e após o provisionamento
   - Conferir que aparecem: `agent_tool_calls_total{tool="provision_platform_instance",status="ok"}`, `agent_watcher_polls_total{result="pending|ready"}`, `agent_watcher_duration_seconds_*`, `provisioning_total{outcome="started"}`
   - Validar formato Prometheus (sample, type, help) e que counters incrementam entre chamadas

### Brainstorms abertos

- `docs/brainstorms/2026-05-17-e2e-testing-without-external-chats.md` — pipeline E2E em cluster efêmero (k3d/vcluster), gitops mock, Telegram mock, validação de métricas. Próximo: decidir cluster + gitops mock, depois virar spec.

### Backlog

- **Structured logging completo** (`docs/specs/2026-05-16-structured-logging.md`) — JSONL via `LOG_FILE`, `OTLPLogExporter` integration. Avaliar se ainda faz sentido após Ciclo 4 ou consolidar com OTel logs.
- **Restart resilience do watcher** (`docs/specs/2026-05-16-platform-watcher-restart-resilience.md`) — persistir `platform_watches` em SQLite para sobreviver a restarts.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.

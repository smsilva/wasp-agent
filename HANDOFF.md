# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–3 completos em `main`. **Ciclo 4 (OpenTelemetry)** implementado e validado em `dev`, aguardando merge para `main`.

## Current Progress

**Ciclos 1, 2 e 3 em `main`.** Smoke test end-to-end validado em 2026-05-16 (Telegram → GitHub → ArgoCD → Crossplane → watcher → notificação).

### Esta sessão (2026-05-17)

- **Plano OTel Ciclo 4 criado** — `4c4020c`: 8 tasks TDD a partir do spec aprovado.
- **Implementação OTel completa** (Tasks 1–7), TDD estrito com cobertura 100% e ruff clean:
  - `9c0207c` deps OpenTelemetry
  - `25c1863` `telemetry.py` (providers + `@instrument` decorator)
  - `9e03ed6` metric globals (provisioning_counter, watcher_duration, watcher_polls_counter)
  - `fe9ea4c` `conftest.py` reseta telemetry entre testes
  - `2e2cca8` `provision.py` instrumentado (span + counter)
  - `8945a7a` `watcher.py` lifecycle span com `Link(parent_span_ctx)` + métricas de poll/duração
  - `c2d710c` `main.py` importa telemetry e adiciona rota `/metrics`
- **Quick fix de logging** — `24ce281`: `logging.basicConfig(level=LOG_LEVEL)` para surfacear INFO logs.
- **Bug fix crítico de `chat_id`** — `dc381fe`: agno 2.0+ usa `session_id = tg:<agent>:<chat_id>:<message_short_id>` (4 partes). `extract_chat_id` usava `parts[-1]` e pegava o hash da mensagem em vez do chat_id → `notify_telegram` recebia chat_id inválido → HTTP 400 silencioso. Corrigido para `parts[2]`, 2 testes cobrindo ambos os formatos.
- **Smoke test E2E validado**: provisionou `wp-smoke2` via Telegram, watcher detectou Ready e enviou notificação proativa. Cleanup feito no gitops repo (`cb9c15e`).
- **Learnings persistidos** em `docs/references/agno.md`:
  - Formato do `session_id` no Telegram com suffix opcional
  - AgentOS reserva `/metrics` e `/metrics/refresh` — não montar Starlette Route duplicado.

### Commits no `dev` ainda não em `main`

```
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
| `docs/specs/2026-05-17-agno-otel-autoinstrumentation.md` | Idea (avaliar `openinference-instrumentation-agno` pós-merge) |
| `docs/specs/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/specs/2026-05-16-structured-logging.md` | Deferred (será absorvido pelo OTel) |

### Plans ativos

| Arquivo | Status |
|---|---|
| `docs/plans/2026-05-17-opentelemetry-cycle4.md` | Tasks 1–7 done, Task 8 (merge) pendente |

## What Worked

- **TDD via subagent** para Tasks 1–7: cobertura 100% mantida desde o início, ruff clean a cada commit.
- **`SpanLink`** (não `set_attribute("parent_span_ctx", ...)`) para correlacionar trabalho assíncrono do watcher ao span síncrono da tool — é o padrão OTel correto para fire-and-forget.
- **Memória do projeto** persistiu a feedback `threading.Thread+asyncio.run` para spawn de async dentro de tool síncrona, evitando regressão.
- **Logging via env var** (`LOG_LEVEL`) como quick fix antes do spec completo de structured logging — destravou diagnóstico do bug do `chat_id` em minutos.

## What Didn't Work

- **Rota `/metrics` shadowed pelo agno**: `app.routes.append(Route("/metrics", ...))` foi silenciosamente sombreado porque agno já registra `/metrics`. Não fatal (Prometheus endpoint funciona, mas serve resposta do agno). Follow-up: mover para `/prom-metrics`.
- **Default logging WARNING** escondeu logs do watcher por toda a primeira execução do smoke test — investigação cega até adicionar `basicConfig`.
- **Suposição errada sobre `session_id`**: assumi formato de 3 partes baseado em código histórico; agno 2.0+ adicionou suffix de message hash. Lição: sempre `peek` no `agent.db` antes de confiar no formato.

## Next Steps

1. **Task 8: Merge `dev` → `main`** — `git checkout main && git pull && git merge --no-ff dev && git push origin main`. Depois arquivar `docs/specs/2026-05-17-opentelemetry-design.md` e `docs/plans/2026-05-17-opentelemetry-cycle4.md` em `archived/` (per CLAUDE.md §7).
2. **Promover spec idea → draft** — `docs/specs/2026-05-17-agno-otel-autoinstrumentation.md` (avaliar `openinference-instrumentation-agno` para ganhar spans de LLM/agent run conectados na mesma trace).
3. **Follow-up: `DeprecationWarning`** de `asyncio.iscoroutinefunction` em `telemetry.py:83` (Python 3.16+). Trocar por `inspect.iscoroutinefunction`.

### Backlog

- **Structured logging completo** (`docs/specs/2026-05-16-structured-logging.md`) — JSONL via `LOG_FILE`, `OTLPLogExporter` integration. Avaliar se ainda faz sentido após Ciclo 4 ou consolidar com OTel logs.
- **Restart resilience do watcher** (`docs/specs/2026-05-16-platform-watcher-restart-resilience.md`) — persistir `platform_watches` em SQLite para sobreviver a restarts.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.

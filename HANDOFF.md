# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–5 completos e em `main`.

## Current Progress

**Ciclos 1–6 em `main`.** `dev` == `main`, working tree limpo.

**Ciclo 6 (2026-05-21, mergeado em `main`):**

1. `NOTIFIER` → `WASP_AGENT_NOTIFIER` (convenção `WASP_AGENT_`).
2. `PROMETHEUS_METRICS_ACTIVE` adicionada ao `.env.example`.
3. `agno` atualizado de 2.6.5 → 2.6.8.
4. Fix de isolamento de testes com `OTEL_EXPORTER_OTLP_ENDPOINT` (`CLAUDE.md §18`).
5. `make e2e-with-debug` + `scripts/e2e-with-debug`.
6. Fix do fixture E2E: patch em `_select_notifier` em vez de `TelegramNotifier` (`CLAUDE.md §19`).
7. Pipeline CI `pull-request.yaml`: lint + testes unitários sempre; E2E condicional (paths relevantes ou label `run-e2e`).

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-20-local-chat.md` | Implemented (2026-05-20) |
| `docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md` | Approved (2026-05-21) — plano em `03-execution/2026-05-21-auth-multichannel-plan.md` |
| `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` | Idea — opção A (OAuth direto GitHub/Google), concorre com cognito-federation |
| `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` | Idea — opção B (Cognito como hub federado), concorre com cli-device-flow |
| `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-persistent-audit-log.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` | Idea |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/sdlc/02-design/2026-05-16-structured-logging.md` | Deferred (avaliar consolidação com OTel logs / audit log) |

### Plans ativos

- `docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md` — **próximo a executar.** 9 tasks, TDD passo-a-passo.

Plano `docs/sdlc/03-execution/2026-05-20-local-chat-plan.md` foi executado — arquivar para `archived/` após merge para `main` (CLAUDE.md §7).

### Open Security Issues

Nenhuma issue ativa em `docs/security/issues/` (só `archived/`).

## What Worked

- **Grilling antes do spec**: fechar todas as decisões de design antes de escrever código eliminou retrabalho
- **Notifier Protocol**: desacopla o watcher do canal desde o início; `RecordingNotifier` torna os testes limpos sem mocks; `ConsoleNotifier` reaproveita o mesmo Protocol para path D sem tocar no watcher
- **TDD via subagent** para Ciclos 4 e 5: cobertura 100% mantida desde o início, ruff clean a cada commit
- **TDD passo-a-passo do plano local-chat**: 7 commits pequenos (red → green → lint → commit por task) manteve cobertura 100% durante toda a execução
- **`SpanLink`** para correlacionar trabalho assíncrono do watcher ao span síncrono da tool — padrão OTel correto para fire-and-forget
- **`make smoke` + Jaeger** — validação E2E de spans sem precisar de infraestrutura permanente
- **Defender no tool layer, não no prompt**: LLMs pequenos (llama3.1 8B) violam regras negativas do system prompt; idempotência na tool + roteamento explícito de notifier são mais robustos que prompt engineering
- **Diagnóstico via tmux**: identificar que `OTEL_EXPORTER_OTLP_ENDPOINT` setado no shell quebra os testes (interação com mocks do conftest)
- **`make e2e-with-debug`**: `-s --log-cli-level=DEBUG -x` + log em disco identificou rapidamente que o watcher notificou via `ConsoleNotifier` em vez de `RecordingNotifier` — bug silencioso que com `make e2e` apenas aparecia como `TimeoutError`

## What Didn't Work

- **Rota `/metrics`**: agno reserva esse path. Movido para `/telemetry/prometheus`
- **Default logging WARNING** escondeu logs do watcher na primeira execução do smoke test
- **Suposição errada sobre `session_id`**: agno 2.0+ adiciona suffix de message hash (4 partes, não 3)
- **`PROMETHEUS_PORT=1`** era semanticamente confuso — variável renomeada para `PROMETHEUS_METRICS_ACTIVE`
- **Instrução de confirmação no system prompt**: llama3.1 8B viola — chama a tool em "request" E novamente em "confirm". Solução não é endurecer o prompt; é tornar a tool idempotente.
- **Seleção global de notifier por env (`TELEGRAM_TOKEN`)**: falha quando múltiplos canais coexistem. Roteamento deve ser por canal de origem do request.
- **`uv sync` sem `uv cache clean`** não resolve instalação corrompida de pacote; `rm -rf .venv && uv sync` também não quando o problema é a cache do `uv` — nesses casos, upgrade de versão ou `uv cache clean <pkg>` é necessário.
- **Patchear `TelegramNotifier` no fixture E2E**: não funciona quando `WASP_AGENT_NOTIFIER=console` está no `.env` — `_select_notifier` retorna antes de chamar `TelegramNotifier`. Patch correto é em `_select_notifier` diretamente.

## Next Steps

### 1. Executar plano auth-multichannel

`docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md`. TDD task-by-task, 9 tasks. Bloqueia security review (CLAUDE.md §9).

**Risco aberto:** Task 3 (handler `/start <token>`) depende de investigação prévia do agno Telegram interface — pode exigir fallback se a integração não permitir registrar handler limpo.

### 2. Smoke test Telegram (manual)

Validar canal Telegram após as mudanças do ciclo 6 (notifier roteia por canal `tg`). **Não exige cluster.** Seguir `docs/runbooks/telegram-local-dev.md`. Pode ser feito antes ou depois do plano auth.

## Backlog

- **LLM behavior evaluation** (`docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md`, Idea) — golden set para detectar regressões no system prompt.
- **Persistent audit log** (`docs/sdlc/02-design/2026-05-20-persistent-audit-log.md`, Idea) — OTel logs export permanente. Pode consolidar com structured-logging deferred.
- **Token/cost budget alerts** (`docs/sdlc/02-design/2026-05-20-token-cost-budget.md`, Idea).
- **Structured logging completo** (`docs/sdlc/02-design/2026-05-16-structured-logging.md`, Deferred) — JSONL via `LOG_FILE`, `OTLPLogExporter`. Avaliar consolidação com OTel logs / audit log.
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
- **CLI/web auth real** — duas opções concorrentes em `Idea`, decidir entre elas antes de promover qualquer uma a Draft:
  - Opção A: `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` — OAuth direto com GitHub + Google.
  - Opção B: `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` — Cognito como hub federado (alinha com `aws-saas-platform`).
  - Gatilho de decisão: existência da CLI `wasp` concreta + escolha entre standalone (A) vs AWS-bound (B).
- **Security review** — após executar plano auth-multichannel (CLAUDE.md §9).
# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–5 completos e em `main`.

## Current Progress

**Ciclos 1–5 em `main`.** Pipeline E2E completo e validado localmente em 2026-05-20. `dev` está 10 commits à frente de `main` (3 commits anteriores de destravamento E2E + 7 commits do path D) — aguardando PR para acionar workflow E2E em CI.

**Path D — Local chat** implementado em 2026-05-20 (7 commits TDD, cobertura 100%, ruff clean). Conversa via `curl` sem Telegram: `make local-chat`, `scripts/local-chat`. Base para `waspctl` futura. Script de roteiro renomeado para `scripts/local-chat-scenario` (era `local-chat-roteiro`) e mensagens traduzidas para inglês.

**Automação GitOps cluster** (2026-05-20, ainda non-commit em `dev`): `make gitops-up` / `make gitops-down` automatizam todos os passos do runbook `docs/runbooks/k3d-argocd-wasp-gitops.md` (cluster k3d `k3s-default` + ArgoCD + Crossplane + Application `wasp-gitops` + provider-kubernetes + function-patch-and-transform + XRD/Composition). Validado fim-a-fim — `wasp-gitops` ficou `Synced/Healthy` com `Platform/test-smoke` provisionada. Runbook colapsou a §2 redundante (o `run` do repo `smsilva/kubernetes` já chama `crossplane-install.sh`).

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-20-local-chat.md` | Implemented (2026-05-20) |
| `docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md` | Idea — **prioridade alta** |
| `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-persistent-audit-log.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` | Idea |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/sdlc/02-design/2026-05-16-structured-logging.md` | Deferred (avaliar consolidação com OTel logs / audit log) |

### Plans ativos

Nenhum. Plano `docs/sdlc/03-execution/2026-05-20-local-chat-plan.md` foi executado nesta sessão — arquivar para `archived/` após merge para `main` (CLAUDE.md §7).

## What Worked

- **Grilling antes do spec**: fechar todas as decisões de design antes de escrever código eliminou retrabalho
- **Notifier Protocol**: desacopla o watcher do canal desde o início; `RecordingNotifier` torna os testes limpos sem mocks; `ConsoleNotifier` reaproveita o mesmo Protocol para path D sem tocar no watcher
- **TDD via subagent** para Ciclos 4 e 5: cobertura 100% mantida desde o início, ruff clean a cada commit
- **TDD passo-a-passo do plano local-chat**: 7 commits pequenos (red → green → lint → commit por task) manteve cobertura 100% durante toda a execução
- **`SpanLink`** para correlacionar trabalho assíncrono do watcher ao span síncrono da tool — padrão OTel correto para fire-and-forget
- **`make smoke` + Jaeger** — validação E2E de spans sem precisar de infraestrutura permanente
- **Instrução de confirmação explícita** no system prompt: `"Never call provision_platform_instance without explicit user confirmation. On the first turn of any creation or deletion request, always ask the user to confirm..."` — formulação mais prescritiva funciona melhor que instrução genérica

## What Didn't Work

- **Rota `/metrics`**: agno reserva esse path. Movido para `/telemetry/prometheus`
- **Default logging WARNING** escondeu logs do watcher na primeira execução do smoke test
- **Suposição errada sobre `session_id`**: agno 2.0+ adiciona suffix de message hash (4 partes, não 3)
- **`PROMETHEUS_PORT=1`** era semanticamente confuso — variável renomeada para `PROMETHEUS_METRICS_ACTIVE`

## Next Steps

### 1. Smoke test Telegram (manual)

Validar o canal Telegram + comportamento do LLM após as mudanças recentes (system prompt de confirmação). **Não exige cluster.**

Alternativa rápida sem ngrok/bot: path D (`docs/runbooks/local-chat.md`) — `unset TELEGRAM_TOKEN && make run` num terminal, `make local-chat` em outro.

Pré-requisito Telegram: ngrok + webhook — seguir `docs/runbooks/telegram-local-dev.md`.

1. `make run` — agente local na porta 7777
2. No Telegram, exercitar:
   - Mensagem qualquer → bot responde
   - `"My name is X"` / `"What is my name?"` → memória de sessão
   - `"Create a platform named test"` → bot **pede confirmação**, não chama a tool sozinho
   - Recusar → bot não chama a tool

Validação fim-a-fim do ciclo real (com cluster ArgoCD + Crossplane) está no apêndice de `docs/runbooks/validation.md`, não é parte do smoke test.

### 2. Validar Prometheus

Independente do Telegram:

- Standalone: `make smoke-prometheus`
- Integrado: `PROMETHEUS_METRICS_ACTIVE=true make run` e `curl http://localhost:7777/telemetry/prometheus | grep agent_`

### 3. PR `dev` → `main`

`dev` está vários commits à frente (path D + multi-LLM provider + log no provision + automação GitOps). Abrir PR para acionar workflow E2E em CI e mover tudo para `main`. Após merge, arquivar `docs/sdlc/03-execution/2026-05-20-local-chat-plan.md` para `archived/`.

### 4. Próximo spec — chat-id allowlist (prioridade alta)

`docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md` está em `Idea`. Próximo passo: promover a `Draft` (design completo) e depois `Approved` (criar plano em `docs/sdlc/03-execution/`). Pré-requisito para o security review (CLAUDE.md §9).

## Backlog

- **LLM behavior evaluation** (`docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md`, Idea) — golden set para detectar regressões no system prompt.
- **Persistent audit log** (`docs/sdlc/02-design/2026-05-20-persistent-audit-log.md`, Idea) — OTel logs export permanente. Pode consolidar com structured-logging deferred.
- **Token/cost budget alerts** (`docs/sdlc/02-design/2026-05-20-token-cost-budget.md`, Idea).
- **Structured logging completo** (`docs/sdlc/02-design/2026-05-16-structured-logging.md`, Deferred) — JSONL via `LOG_FILE`, `OTLPLogExporter`. Avaliar consolidação com OTel logs / audit log.
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
- **Security review** — após implementar chat-id allowlist (CLAUDE.md §9).

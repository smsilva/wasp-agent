# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–5 completos e em `main`.

## Current Progress

**Ciclos 1–5 em `main`.** Pipeline E2E completo e validado localmente em 2026-05-20. `dev` está vários commits à frente de `main` — aguardando PR.

**Path D — Local chat** implementado em 2026-05-20 (cobertura 100%, ruff clean). Conversa via `curl` sem Telegram: `make local-chat`, `scripts/local-chat`. Script de roteiro `scripts/local-chat-scenario` agora gera tenant name único por execução (`test-smoke-YYYYMMDD-HHMMSS`).

**Automação GitOps cluster** (2026-05-20, committed em `dev`): `make gitops-up` / `make gitops-down` automatizam todos os passos do runbook.

**Sessão 2026-05-20 (uncommitted em `dev`):** dois bugs do smoke local-chat corrigidos no tool layer + roteamento de notifier por canal de origem:

1. **`provision_platform_instance` agora é idempotente.** LLM (llama3.1 8B via Ollama) disparava a tool duas vezes (step "request" + step "confirm") apesar do system prompt — segunda chamada quebrava com `GithubException 422 "sha wasn't supplied"`. Fix: nova `FileAlreadyExistsError` em `wasp/git_client.py` (traduz 422 do PyGithub) + catch em `wasp/provision.py` retornando `status: "already_provisioning"` sem spawnar watcher duplicado.
2. **Notifier roteia por canal de origem.** Com `TELEGRAM_TOKEN` setado, `_select_notifier()` sempre retornava `TelegramNotifier` mesmo para requests do `local-chat` — notificações falhavam silenciosamente (POST sendMessage → 400). Fix: novo `extract_channel(run_context)` em `wasp/watcher.py` lê prefixo do `session_id` (`tg` / `local`); `_select_notifier(channel)` em `wasp/provision.py` roteia por canal por padrão (env `NOTIFIER` ainda sobrepõe). CLAUDE.md §14 atualizado.

100% coverage mantido (330 stmts), ruff clean, 79 testes passando.

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

Nenhum. Plano `docs/sdlc/03-execution/2026-05-20-local-chat-plan.md` foi executado — arquivar para `archived/` após merge para `main` (CLAUDE.md §7).

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

## What Didn't Work

- **Rota `/metrics`**: agno reserva esse path. Movido para `/telemetry/prometheus`
- **Default logging WARNING** escondeu logs do watcher na primeira execução do smoke test
- **Suposição errada sobre `session_id`**: agno 2.0+ adiciona suffix de message hash (4 partes, não 3)
- **`PROMETHEUS_PORT=1`** era semanticamente confuso — variável renomeada para `PROMETHEUS_METRICS_ACTIVE`
- **Instrução de confirmação no system prompt** (`"Never call provision_platform_instance without explicit user confirmation..."`): llama3.1 8B viola — chama a tool em "request" E novamente em "confirm". Solução não é endurecer o prompt; é tornar a tool idempotente (ver "Current Progress" item 1).
- **Seleção global de notifier por env (`TELEGRAM_TOKEN`)**: falha quando múltiplos canais coexistem (Telegram + local-chat). Roteamento deve ser por canal de origem do request.

## Next Steps

### 1. Commit + smoke retest

Mudanças desta sessão estão uncommitted em `dev`. Commitar (sugestão de mensagens):

- `fix(provision): idempotent create when manifest already exists`
- `fix(provision): select notifier by session channel, not env`
- `chore(scripts): unique tenant name per local-chat-scenario run`

Depois rodar `make run` + `bash scripts/local-chat-scenario` e confirmar no stdout do `make run`:
- `[NOTIFIER chat_id=...] Plataforma 'X' está pronta...` (ConsoleNotifier ativo)
- Sem `GithubException 422` mesmo se o LLM chamar a tool duas vezes
- Sem POST para `api.telegram.org` quando origem é `local`

### 2. Smoke test Telegram (manual)

Validar canal Telegram após as mudanças (notifier agora roteia por canal `tg`). **Não exige cluster.** Seguir `docs/runbooks/telegram-local-dev.md`.

### 3. Validar Prometheus

Independente: `PROMETHEUS_METRICS_ACTIVE=true make run` e `curl http://localhost:7777/telemetry/prometheus | grep agent_`.

### 4. PR `dev` → `main`

`dev` está vários commits à frente (path D + multi-LLM provider + log no provision + automação GitOps + fixes desta sessão). Abrir PR para acionar workflow E2E em CI. Após merge, arquivar `docs/sdlc/03-execution/2026-05-20-local-chat-plan.md` para `archived/`.

### 5. Próximo spec — chat-id allowlist (prioridade alta)

`docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md` está em `Idea`. Próximo passo: promover a `Draft` (design completo) e depois `Approved` (criar plano em `docs/sdlc/03-execution/`). Pré-requisito para o security review (CLAUDE.md §9).

## Backlog

- **LLM behavior evaluation** (`docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md`, Idea) — golden set para detectar regressões no system prompt. Reforçado pelo achado desta sessão: llama3.1 8B viola a regra de confirmação.
- **Persistent audit log** (`docs/sdlc/02-design/2026-05-20-persistent-audit-log.md`, Idea) — OTel logs export permanente. Pode consolidar com structured-logging deferred.
- **Token/cost budget alerts** (`docs/sdlc/02-design/2026-05-20-token-cost-budget.md`, Idea).
- **Structured logging completo** (`docs/sdlc/02-design/2026-05-16-structured-logging.md`, Deferred) — JSONL via `LOG_FILE`, `OTLPLogExporter`. Avaliar consolidação com OTel logs / audit log.
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
- **Security review** — após implementar chat-id allowlist (CLAUDE.md §9).
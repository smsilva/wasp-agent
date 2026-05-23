# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–6 completos e em `main`.

## Current Progress

**Ciclos 1–6 + logging em `dev`**, não merged para `main` ainda. `dev` está 12 commits à frente de `origin/dev` (não pushed).

**Sessão 2026-05-23 — Logging:**

Implementação completa do subsistema de logging em `dev`:

- `wasp/logging.py` — `JSONFormatter`, `chat_id_var` (ContextVar), `_RotatingTimedFileHandler`, `configure_logging()`
- `main.py` — substitui `logging.basicConfig()` por `configure_logging()`
- `wasp/telemetry.py` — `LoggingInstrumentor` wired (bridge OTel → Python logging)
- `wasp/provision.py` / `wasp/watcher.py` — propagação de `chat_id` via ContextVar; campo `platform` nos logs-chave
- Rotação automática: diária (midnight UTC) + 50 MB; 7 backups; configurável via `LOG_FILE_MAX_BYTES` / `LOG_FILE_BACKUP_COUNT`
- `scripts/e2e-with-debug` — usa `LOG_FORMAT=json` (saída JSONL)
- 22 testes unitários, cobertura 100%, ruff clean
- Validado: `make run` (texto) + `make e2e-with-debug` (JSONL com `chat_id` e `platform`)
- Specs supersedidos arquivados: `2026-05-16-structured-logging.md`, `2026-05-20-persistent-audit-log.md`

**Sessão 2026-05-21:**

1. Arquivado `docs/sdlc/03-execution/2026-05-20-local-chat-plan.md`.
2. Smoke test Telegram (manual) validado: memória de sessão OK; canal `tg` routing OK.
3. Validação fim-a-fim GitOps (manual) rodada com sucesso.
4. `fix(gitops)`: inverte ordem no `scripts/gitops-up` — XRD/Composition antes de ArgoCD Application.
5. Arquivado `docs/sdlc/03-execution/2026-05-21-ci-pull-request.md`.

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md` | Approved — plano em `03-execution/2026-05-21-auth-multichannel-plan.md` |
| `docs/sdlc/02-design/2026-05-21-ci-pull-request.md` | Implemented (não arquivado) |
| `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` | Idea — opção A (OAuth direto GitHub/Google), concorre com cognito-federation |
| `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` | Idea — opção B (Cognito como hub federado), alinha com `aws-saas-platform` |
| `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` | Idea |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |

### Plans ativos

- `docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md` — pronto para execução.

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
- **Validação manual do ciclo GitOps real**: subir cluster + tentar `make gitops-up` expôs ordem incorreta do script (Application antes do XRD); smoke automatizado não cobre isso porque usa `fake_reconciler`
- **ContextVar para propagação de `chat_id`**: propaga contexto cross-thread sem passar explicitamente por toda a call chain; `watch_platform` chama `chat_id_var.set(chat_id)` no início do thread novo

## What Didn't Work

- **Rota `/metrics`**: agno reserva esse path. Movido para `/telemetry/prometheus`
- **Default logging WARNING** escondeu logs do watcher na primeira execução do smoke test
- **Suposição errada sobre `session_id`**: agno 2.0+ adiciona suffix de message hash (4 partes, não 3)
- **`PROMETHEUS_PORT=1`** era semanticamente confuso — variável renomeada para `PROMETHEUS_METRICS_ACTIVE`
- **Instrução de confirmação no system prompt**: llama3.1 8B viola — chama a tool em "request" E novamente em "confirm". Solução não é endurecer o prompt; é tornar a tool idempotente.
- **Seleção global de notifier por env (`TELEGRAM_TOKEN`)**: falha quando múltiplos canais coexistem. Roteamento deve ser por canal de origem do request.
- **`uv sync` sem `uv cache clean`** não resolve instalação corrompida de pacote; `rm -rf .venv && uv sync` também não quando o problema é a cache do `uv` — nesses casos, upgrade de versão ou `uv cache clean <pkg>` é necessário.
- **Patchear `TelegramNotifier` no fixture E2E**: não funciona quando `WASP_AGENT_NOTIFIER=console` está no `.env` — `_select_notifier` retorna antes de chamar `TelegramNotifier`. Patch correto é em `_select_notifier` diretamente.
- **Ordem original do `scripts/gitops-up`**: aplicava ArgoCD `Application` antes do XRD/Composition de Platform; ArgoCD sincronizava `infrastructure/tenants` e quebrava com `no matches for kind "Platform"`.

## Next Steps

### 1. Executar plano auth-multichannel

`docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md`. TDD task-by-task, 9 tasks. Bloqueia security review (CLAUDE.md §9).

**Risco aberto:** Task 3 (handler `/start <token>`) depende de investigação prévia do agno Telegram interface — pode exigir fallback se a integração não permitir registrar handler limpo.

## Backlog

- **LLM behavior evaluation** (`docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md`, Idea) — golden set para detectar regressões no system prompt.
- **Token/cost budget alerts** (`docs/sdlc/02-design/2026-05-20-token-cost-budget.md`, Idea).
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
- **CLI/web auth real** — duas opções concorrentes em `Idea`, decidir entre elas antes de promover qualquer uma a Draft:
  - Opção A: `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` — OAuth direto com GitHub + Google.
  - Opção B: `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` — Cognito como hub federado (alinha com `aws-saas-platform`).
  - Gatilho de decisão: existência da CLI `wasp` concreta + escolha entre standalone (A) vs AWS-bound (B).
- **Security review** — após executar plano auth-multichannel (CLAUDE.md §9).
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`.

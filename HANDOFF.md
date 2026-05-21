# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–6 completos e em `main`.

## Current Progress

**Ciclos 1–6 em `main`.** `dev` está 2 commits à frente de `origin/dev` (housekeeping, não merged ainda).

**Sessão 2026-05-21:**

1. `fd5f8a2` — Arquivado `docs/sdlc/03-execution/2026-05-20-local-chat-plan.md` (executado no Ciclo 6).
2. **Smoke test Telegram (manual)** validado: ngrok + webhook + `make run` + sequência "Meu nome é João" / "Qual é o meu nome?" — memória de sessão OK; canal `tg` routing OK.
3. **Validação fim-a-fim GitOps (manual)** rodada com sucesso (`make gitops-up` inicial falhou por ordem dos manifestos).
4. `0949568` — `fix(gitops): apply Crossplane XRD/Composition before ArgoCD Application`. Inverte passos no `scripts/gitops-up` e em `docs/runbooks/k3d-argocd-wasp-gitops.md`: Application `wasp-gitops` agora é aplicada **depois** do XRD/Composition de Platform (antes, sync quebrava com `no matches for kind "Platform"`).
5. `34a5dc3` — Arquivado `docs/sdlc/03-execution/2026-05-21-ci-pull-request.md` (executado em `main`).

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-20-local-chat.md` | Implemented (2026-05-20) |
| `docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md` | Approved (2026-05-21) — plano em `03-execution/2026-05-21-auth-multichannel-plan.md` |
| `docs/sdlc/02-design/2026-05-21-ci-pull-request.md` | Implemented — plano em `03-execution/2026-05-21-ci-pull-request.md` (não arquivado ainda) |
| `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` | Idea — opção A (OAuth direto GitHub/Google), concorre com cognito-federation |
| `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` | Idea — opção B (Cognito como hub federado), concorre com cli-device-flow |
| `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-persistent-audit-log.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` | Idea |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/sdlc/02-design/2026-05-16-structured-logging.md` | Deferred (avaliar consolidação com OTel logs / audit log) |

### Plans ativos

- `docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md` — aguardando execução (após logging).

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

## What Didn't Work

- **Rota `/metrics`**: agno reserva esse path. Movido para `/telemetry/prometheus`
- **Default logging WARNING** escondeu logs do watcher na primeira execução do smoke test
- **Suposição errada sobre `session_id`**: agno 2.0+ adiciona suffix de message hash (4 partes, não 3)
- **`PROMETHEUS_PORT=1`** era semanticamente confuso — variável renomeada para `PROMETHEUS_METRICS_ACTIVE`
- **Instrução de confirmação no system prompt**: llama3.1 8B viola — chama a tool em "request" E novamente em "confirm". Solução não é endurecer o prompt; é tornar a tool idempotente.
- **Seleção global de notifier por env (`TELEGRAM_TOKEN`)**: falha quando múltiplos canais coexistem. Roteamento deve ser por canal de origem do request.
- **`uv sync` sem `uv cache clean`** não resolve instalação corrompida de pacote; `rm -rf .venv && uv sync` também não quando o problema é a cache do `uv` — nesses casos, upgrade de versão ou `uv cache clean <pkg>` é necessário.
- **Patchear `TelegramNotifier` no fixture E2E**: não funciona quando `WASP_AGENT_NOTIFIER=console` está no `.env` — `_select_notifier` retorna antes de chamar `TelegramNotifier`. Patch correto é em `_select_notifier` diretamente.
- **Ordem original do `scripts/gitops-up`**: aplicava ArgoCD `Application` antes do XRD/Composition de Platform; ArgoCD sincronizava `infrastructure/tenants` (instâncias de `Platform`) e quebrava com `no matches for kind "Platform"`. Corrigido em `0949568`.

## Next Steps

### 1. Push `dev` → `origin/dev`

4 commits locais (`fd5f8a2`, `0949568`, `0c70d68`, `34a5dc3`) ainda não pushed.

### 2. Logging — consolidar specs e implementar

**Próximo tema**, antes de auth-multichannel. Dois specs a fundir em um único design:

- `docs/sdlc/02-design/2026-05-16-structured-logging.md` (Deferred) — JSONL via `LOG_FILE`.
- `docs/sdlc/02-design/2026-05-20-persistent-audit-log.md` (Idea) — OTLP export permanente; o próprio spec pede consolidação com o anterior.

Decisão central: até onde levar sem overengineering (projeto pessoal). Mínimo viável é `LOG_FILE` JSONL; teto é OTLP → backend externo (Tempo, Honeycomb, etc.). Logging vem antes de auth porque a identidade do chat-id allowlist agrega valor de auditoria — faz sentido ter o trail pronto primeiro.

### 3. Executar plano auth-multichannel

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
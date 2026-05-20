# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–5 completos e em `main`.

## Current Progress

**Ciclos 1–5 em `main`.** Pipeline E2E completo e validado em 2026-05-20.

### Esta sessão (2026-05-20) — destravar E2E + qualidade

Mudanças locais ainda não commitadas:

- **System prompt reforçado** (`main.py`): instrução explícita de confirmação antes de qualquer tool call — resolve o bloqueio de LLM que fazia Claude Haiku 4.5 provisionar sem pedir confirmação
- **`PROMETHEUS_PORT` → `PROMETHEUS_METRICS_ACTIVE`**: variável renomeada em `telemetry.py`, `smoke_prometheus.py`, `tests/test_telemetry.py`, `Makefile`; semântica mais clara (flag booleano, não número de porta)
- **`make e2e`, `make k3d-up`, `make k3d-down`** adicionados ao `Makefile`; `scripts/k3d-up` e `scripts/k3d-down` criados
- **Fixtures E2E melhoradas** (`tests/e2e/conftest.py`):
  - Cleanup explícito no início (`docker rm -f wasp-e2e-gitea`, `k3d cluster delete`) para ambientes sujos
  - Session IDs únicos por teste (`uuid4`) para evitar contaminação do `agent.db` entre execuções
  - `_telemetry.configure()` explícito depois do `monkeypatch.setenv("PROMETHEUS_METRICS_ACTIVE")` — necessário porque o módulo já executou `configure()` no import
- **Assertion error messages** incluem o SSE response completo para facilitar diagnóstico
- **`CLAUDE.md §15`**: convenção "multi-line Makefile → scripts/" documentada

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-19-e2e-testing-pipeline.md` | Implemented |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/sdlc/02-design/2026-05-16-structured-logging.md` | Deferred (avaliar consolidação com OTel logs) |

### Plans ativos

Nenhum plano em andamento.

## What Worked

- **Grilling antes do spec**: fechar todas as decisões de design antes de escrever código eliminou retrabalho
- **Notifier Protocol**: desacopla o watcher do canal desde o início; `RecordingNotifier` torna os testes limpos sem mocks
- **TDD via subagent** para Ciclos 4 e 5: cobertura 100% mantida desde o início, ruff clean a cada commit
- **`SpanLink`** para correlacionar trabalho assíncrono do watcher ao span síncrono da tool — padrão OTel correto para fire-and-forget
- **`make smoke` + Jaeger** — validação E2E de spans sem precisar de infraestrutura permanente
- **Instrução de confirmação explícita** no system prompt: `"Never call provision_platform_instance without explicit user confirmation. On the first turn of any creation or deletion request, always ask the user to confirm..."` — formulação mais prescritiva funciona melhor que instrução genérica

## What Didn't Work

- **Rota `/metrics`**: agno reserva esse path. Movido para `/telemetry/prometheus`
- **Default logging WARNING** escondeu logs do watcher na primeira execução do smoke test
- **Suposição errada sobre `session_id`**: agno 2.0+ adiciona suffix de message hash (4 partes, não 3)
- **`PROMETHEUS_PORT=1`** era semanticamente confuso — variável renomeada para `PROMETHEUS_METRICS_ACTIVE`

## Next Steps

### 1. Arquivar spec e plano do pipeline E2E

Mover para `archived/`:
- `docs/sdlc/02-design/2026-05-19-e2e-testing-pipeline.md`
- `docs/sdlc/03-execution/2026-05-19-e2e-testing-pipeline.md`
- `docs/sdlc/01-exploration/2026-05-17-e2e-testing-without-external-chats.md`

### 2. Smoke test Telegram + Prometheus

Validar o fluxo completo com Telegram e checar métricas Prometheus depois das mudanças recentes:

1. `make k3d-up` — cluster local persistente
2. `PROMETHEUS_METRICS_ACTIVE=true` no `.env`
3. `make run` — agente local
4. ngrok para webhook Telegram (ver `docs/runbooks/telegram-local-dev.md`)
5. Testar via Telegram: provisionar plataforma, verificar notificação
6. `curl http://localhost:7777/telemetry/prometheus | grep agent_provisioning`

### Pipeline E2E — CI

Workflow `.github/workflows/e2e.yaml` pronto. Pendente: validação em PR real para `dev` (independe do passo 1 acima; CI usa o mesmo modelo via secrets).

## Backlog

- **Structured logging completo** (`docs/sdlc/02-design/2026-05-16-structured-logging.md`) — JSONL via `LOG_FILE`, `OTLPLogExporter` integration. Avaliar consolidação com OTel logs do Ciclo 5.
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`) — persistir `platform_watches` em SQLite para sobreviver a restarts.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
- **Autenticação/autorização** — allowlist de `chat_id` no bot; security review após isso.
- Arquivar `docs/sdlc/01-exploration/2026-05-17-e2e-testing-without-external-chats.md` (supersedido).

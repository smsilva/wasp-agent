# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–5 completos e em `main`.

## Current Progress

**Ciclos 1–5 em `main`.** Pipeline E2E completo. `dev` tem mudanças uncommitted — aguardando commit e PR.

**Sessão 2026-05-21 (uncommitted em `dev`):**

1. **`NOTIFIER` renomeada para `WASP_AGENT_NOTIFIER`.** Convenção `WASP_AGENT_` para variáveis de configuração do agent. Arquivos afetados: `wasp/provision.py`, `tests/test_provision.py`, `.env.example`, `CLAUDE.md`, `HANDOFF.md`, `docs/runbooks/local-chat.md`.
2. **`PROMETHEUS_METRICS_ACTIVE` adicionada ao `.env.example`.**
3. **`agno` atualizado de 2.6.5 → 2.6.8** no `uv.lock`.
4. **`conftest.py` — fix de isolamento de testes com OTEL.** O fixture `mock_agno` agora faz `monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)`. Sem isso, ambientes com SigNoz/Jaeger configurado no shell quebram todos os testes. Documentado em `CLAUDE.md §18`.
5. **`make e2e-with-debug` + `scripts/e2e-with-debug`.** Novo target para debugging: `-s --log-cli-level=DEBUG -x`, grava log em `logs/e2e-<timestamp>.log`, imprime o caminho ao final.
6. **Fix do fixture E2E (`tests/e2e/conftest.py`).** O `agent_client` agora patcheia `_select_notifier` diretamente (em vez de `TelegramNotifier`). Raiz do bug: `WASP_AGENT_NOTIFIER=console` no `.env` é carregado por `load_dotenv()` em `main.py` no import — `_select_notifier` retornava `ConsoleNotifier` antes de chegar na chamada de `TelegramNotifier`, silenciosamente ignorando o patch. Teste falhava com `TimeoutError`. Documentado em `CLAUDE.md §19`.

`make e2e-with-debug` executado com sucesso: **1 passed in 53.20s**.

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

### 1. Smoke test Telegram (manual)

Validar canal Telegram após as mudanças (notifier agora roteia por canal `tg`). **Não exige cluster.** Seguir `docs/runbooks/telegram-local-dev.md`.

### 3. Próximo spec — chat-id allowlist (prioridade alta)

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
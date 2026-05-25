# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão, autenticação multi-canal por invite, e suporte futuro a Discord/Slack.

Ciclos 1–6 estão em `main`. Ciclo 7 (autenticação multi-canal) + logging estruturado estão em `dev`.

## Current Progress

**Sessão 2026-05-25 — Security review do Ciclo 7 (auth multi-canal)**

- SEC-004 (High, resolved): TOCTOU race em `redeem_invite` — `BEGIN IMMEDIATE` antes do SELECT; teste threading com `threading.Barrier` adicionado em `test_redeem_invite_concurrent_unbound_token_only_succeeds_once`.
- SEC-005 (Low, resolved): `wasp_auth_denied_total{reason="invalid_token"}` não emitida quando invite inválido — `telemetry.auth_denied` adicionado em `_process_start_token`; assertion no teste existente.
- `bootstrap_admin` tornada atômica: `BEGIN IMMEDIATE` + transação única eliminam orphan row em race de bootstrap simultâneo.
- Gate `_initialized_dbs` em `init_db`: set módulo-nível evita 4 DDL statements a cada chamada de `is_authorized`. Reseta por reimport — sem conflito com `conftest.py`.
- Import redundante `starlette.requests.Request` removido de `get_router_with_auth`: PEP 649 (Python 3.14) faz FastAPI resolver annotations via `__globals__` do módulo, não pelo scope da closure. §12a do `CLAUDE.md` atualizado.
- Revisão completa: entropy do token (256 bits), `X-Telegram-Bot-Api-Secret-Token` antes de qualquer processamento, ausência de token nos logs, limitação de first-claimer em invites unbound — todos sem finding ativo.
- `CLAUDE.md §21` adicionado: padrão `BEGIN IMMEDIATE` para check-then-write em `wasp/auth.py`.

**Sessão 2026-05-23 (parte 3) — Validação Telegram completa + documentação**

- Fix: `webhook_with_auth` retornava 422 por ausência de type annotations. Fix: anotar `request: Request` e `background_tasks: BackgroundTasks`. Regression test via `inspect.signature`.
- Fluxo GitOps completo validado: ngrok + webhook + auth bootstrap + `make gitops-up` + confirmação → commit `smsilva/wasp-gitops` → ArgoCD → Crossplane → notificação `Ready` (~2 min).
- `validation.md` expandido para E.1–E.7; `telegram-local-dev.md` separado de setup vs. smoke test completo.

**Sessão 2026-05-23 (parte 2) — Auth multi-canal (Ciclo 7)**

- Plan `docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md` executado fim-a-fim (9 tasks TDD): `wasp/auth.py`, guard em `provision_platform_instance`, handler `/start <token>`, CLI admin, métrica `wasp_auth_denied_total`, `auth.init_db()` no startup, runbook `docs/runbooks/auth-admin.md`.

**Sessão 2026-05-23 (parte 1) — Logging:** `wasp/logging.py`, `JSONFormatter`, `chat_id_var` ContextVar, 22 testes, cobertura 100%.

**Sessão 2026-05-21:** smoke Telegram manual validado; validação GitOps end-to-end; `fix(gitops)` na ordem do `scripts/gitops-up`.

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md` | Implemented |
| `docs/sdlc/02-design/2026-05-20-local-chat.md` | Implemented |
| `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` | Idea — opção A (OAuth direto GitHub/Google) |
| `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` | Idea — opção B (Cognito como hub federado) |
| `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` | Idea |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |

### Plans ativos

Nenhum em execução.

### Open Security Issues

Nenhuma issue ativa em `docs/security/issues/`.

## What Worked

- **`BEGIN IMMEDIATE` antes do SELECT em redeem_invite:** elimina a janela TOCTOU sem alterar a estrutura geral do código; `with con:` subsequente funciona corretamente porque Python's sqlite3 não emite `BEGIN` automático quando `sqlite3_get_autocommit()=0`.
- **Smoke test completo até Ready (~2 min):** fluxo Telegram → commit `smsilva/wasp-gitops` → ArgoCD sync → Crossplane reconcile → notificação funcionou sem intervenção manual.
- **`inspect.signature` para regression tests de type annotations:** testes diretos no endpoint não capturam ausência de anotações FastAPI; `inspect.signature` é o gate correto.
- **threading.Barrier para teste de concorrência SQLite:** garante que ambas as threads entrem em `redeem_invite` simultaneamente, maximizando a janela de race; determinístico o suficiente para ser executado em CI.

## What Didn't Work

- **Importar `Request` localmente dentro da closure:** PEP 649 (Python 3.14) torna annotations deferidas; `get_type_hints(webhook_with_auth)` resolve via `__globals__` do módulo, não pelo scope da closure. ruff F401 estava correto.
- **Testes unitários diretos no `webhook_with_auth`:** passavam sem type annotations porque chamam o endpoint como função Python, bypassando FastAPI. Solução: `inspect.signature` + smoke test manual.

## Next Steps

### 1. Decidir entre opção A (CLI device flow OAuth) e opção B (Cognito federation)

Specs `Idea` em `docs/sdlc/02-design/`. Promover uma para Draft e criar plano de execução.

### 2. Definir prioridade dos demais specs em `Idea`

- `2026-05-20-llm-behavior-evaluation.md` — golden set para detectar regressões no system prompt.
- `2026-05-20-token-cost-budget.md` — alertas de orçamento de tokens.

## Backlog

- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`.
- **Reduzir `MAX_COMPLEXITY` para 10** — refatorar `provision_platform_instance` (`wasp/provision.py`, CC=15) e atualizar limite em `tests/test_complexity.py`.

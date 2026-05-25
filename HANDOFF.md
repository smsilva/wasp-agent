# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão, autenticação multi-canal por invite, e suporte futuro a Discord/Slack.

## Current State

Branch `dev` contém sobre `main`:
- Logging estruturado (`wasp/logging.py`, `JSONFormatter`, `chat_id_var` ContextVar)
- Auth multi-canal (Ciclo 7): `wasp/auth.py`, guard em `provision_platform_instance`, handler `/start <token>`, CLI admin, métrica `wasp_auth_denied_total`, runbook `docs/runbooks/auth-admin.md`
- Security review concluída: sem issues ativas em `docs/security/issues/`

## What Worked

- **`BEGIN IMMEDIATE` antes do SELECT em `redeem_invite`:** elimina a janela TOCTOU sem alterar a estrutura geral do código; `with con:` subsequente funciona corretamente porque Python's sqlite3 não emite `BEGIN` automático quando `sqlite3_get_autocommit()=0`.
- **Smoke test completo até Ready (~2 min):** fluxo Telegram → commit `smsilva/wasp-gitops` → ArgoCD sync → Crossplane reconcile → notificação funcionou sem intervenção manual.

## Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` | Idea — opção A (OAuth direto GitHub/Google) |
| `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` | Idea — opção B (Cognito como hub federado) |
| `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` | Idea |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |

### Plans ativos

Nenhum em execução.

### Open Security Issues

Nenhuma issue ativa em `docs/security/issues/`.

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

# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão, autenticação multi-canal por invite, e suporte futuro a Discord/Slack.

## Current State

`dev` está 1 commit à frente de `main` (nota ruff F401 no CLAUDE.md). `main` tem o código mais completo.

**Entregue nesta sessão (mergeado em `main`):**
- Refatoração `wasp/clients/`: `wasp/notifier.py` e `wasp/telegram.py` reorganizados em subpacotes por canal
  - `wasp/clients/__init__.py` — `Notifier` Protocol
  - `wasp/clients/telegram/` — `TelegramNotifier`, `_install_start_token_handler`, `_process_start_token`
  - `wasp/clients/local/` — `ConsoleNotifier`
  - `tests/notifiers.py` — `RecordingNotifier` (test double)
- `CLAUDE.md §22` — guideline do padrão `clients/` para novos canais
- `docs/sdlc/01-exploration/clients-package-pattern.md` — questões abertas sobre extensão do padrão para `git_client`, `gitops_committer`, `platform_cluster`

**Validação pendente** (requer infraestrutura externa):
- `make e2e-with-debug`
- `make gitops-up`
- `make local-chat`

**Estado anterior a esta sessão** (já em `main`):
- Logging estruturado (`wasp/logging.py`, `JSONFormatter`, `chat_id_var` ContextVar)
- Auth multi-canal (Ciclo 7): `wasp/auth.py`, guard em `provision_platform_instance`, handler `/start <token>`, CLI admin, métrica `wasp_auth_denied_total`
- `provision_platform_instance` refatorado (CC 15→≤10) + tool `list_platform_instances`
- `AuthorizationGuard`, `GitOpsCommitter`, `PlatformClusterReader`, `PlatformWatcherSpawner`, `PlatformProvisioner`, `PlatformInventory`

## Open Security Issues

Nenhuma issue ativa em `docs/security/issues/`.

## Active Specs / Plans

### Status: Idea
- `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` — opção A de auth (OAuth direto GitHub/Google)
- `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` — opção B de auth (Cognito como hub federado)
- `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` — golden set para detectar regressões no system prompt
- `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` — alertas de orçamento de tokens

### Status: Deferred
- `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` — persistir `platform_watches` em SQLite

## Next Steps

1. **Rodar validação pendente:** `make e2e-with-debug` → `make gitops-up` → `make local-chat` (verificar callback no terminal)
2. **Decidir próxima feature:** escolher entre opção A (CLI device flow OAuth) e opção B (Cognito federation), ou avançar em `llm-behavior-evaluation`

## Backlog

- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite
- **Extensão do padrão `clients/`** (`docs/sdlc/01-exploration/clients-package-pattern.md`) — decidir se `git_client`, `gitops_committer` e `platform_cluster` seguem o mesmo padrão ou ficam em `wasp/`
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`
- **Falha clara em configuração ausente** — validar variáveis obrigatórias no startup com mensagens explícitas
- **Authorization granular (RBAC)** — papéis (admin, operator, viewer) e mapeamento `user_id → role`

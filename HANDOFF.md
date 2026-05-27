# Handoff

## Goal

Implementar um agente DevOps multi-canal: bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão, autenticação multi-canal por invite, e suporte a Telegram e Discord.

## Current State

`dev` está 15 commits à frente de `main`.

**Entregue nesta sessão (branch `dev`, aguardando merge):**
- Discord bot completo com feature parity ao Telegram: `wasp/clients/discord/` (`bot.py`, `notifier.py`, `__init__.py`)
- `DiscordBot(discord.Client)` com `on_message` (auth guard + per-user session) e `on_ready` (registra o event loop para bridge cross-loop)
- `DiscordNotifier` com `set_loop()` — bridge via `asyncio.run_coroutine_threadsafe` para enviar notificações do watcher thread para o loop do Discord
- `InterfaceLoader.build_discord()` com singleton `discord_pkg._notifier`
- Lifespan do Discord integrado ao FastAPI via `asynccontextmanager` wrapping do lifespan do agno (necessário porque agno define `lifespan_context` que ignora `on_startup`/`on_shutdown`)
- Routing `"dc"` em `_select_notifier`, `extract_channel`, `extract_chat_id`
- `make admin-link USER_ID=<uid> CHANNEL=dc ID=<id>` — vincula canal adicional a usuário existente sem exigir DB vazio
- `auth_cli link` subcomando + `scripts/admin-link` + target no Makefile
- `docs/runbooks/auth-admin.md` atualizado com seção "Vincular canal adicional"
- Smoke test manual: bot respondendo, provisioning + notificação watcher funcionando via Discord
- 261 testes passando, 100% coverage

**Estado anterior** (já em `main`):
- Pacote `wasp/resources/` com `ResourceManifest`/`MetadataSpec` e `wasp/resources/platform/`
- Pacote `wasp/clients/k8s/` com `KubernetesResourceReader`
- `wasp/provision.py` com dois `@tool` wrappers
- Refatoração `wasp/clients/` por canal (Telegram, local) + `InterfaceLoader`
- Logging estruturado, Auth multi-canal (invite), `make admin-bootstrap/invite/revoke/list`

## Open Security Issues

Nenhuma issue ativa em `docs/security/issues/`.

## Active Specs / Plans

### Status: Approved (implementado, aguardando marcação)
- `docs/superpowers/specs/2026-05-27-discord-bot-design.md` — Discord Bot Design (entregue nesta sessão; mover para Implemented após merge)
- `docs/superpowers/specs/2026-05-26-resources-package-design.md` — Resources Package Design (entregue sessão anterior)
- `docs/superpowers/specs/2026-05-26-interface-loader-design.md` — InterfaceLoader Design (entregue sessão anterior)

### Status: Idea
- `docs/sdlc/02-design/2026-05-27-discord-slash-commands.md` — Discord Slash Commands (próxima extensão natural do Discord)
- `docs/sdlc/02-design/2026-05-26-opentelemetry-tracing.md` — Distributed Tracing
- `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` — golden set para regressões no system prompt
- `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` — alertas de orçamento
- `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` — auth OAuth device flow
- `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` — auth Cognito federation
- 14 specs de 2026-05-26: helm-chart, dora-metrics, rate-limiting, prompt-versioning, load-testing, sbom, supply-chain-security, secret-rotation, code-quality-security-scanning, penetration-test, eu-ai-act, privacy-data-retention, disaster-recovery, incident-response

### Status: Deferred
- `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` — persistir `platform_watches` em SQLite

## Next Steps

1. **Merge `dev` → `main`** — branch passou em `make test` (261 tests), smoke test Discord confirmado
2. **Atualizar status dos specs entregues** — `2026-05-27-discord-bot-design.md`, `2026-05-26-resources-package-design.md`, `2026-05-26-interface-loader-design.md` → `Implemented`
3. **Decidir próxima feature** — sugestões em ordem de valor imediato:
   - `2026-05-27-discord-slash-commands.md` — ergonomia para usuários Discord
   - `2026-05-20-llm-behavior-evaluation.md` — previne regressões silenciosas no system prompt
   - `2026-05-26-opentelemetry-tracing.md` — observabilidade end-to-end

## Backlog

- **Discord slash commands** (`docs/sdlc/02-design/2026-05-27-discord-slash-commands.md`, Idea) — `/provision`, `/list`, `/status` como alternativa à linguagem natural
- **Handler `/start <token>` no Discord** — hoje novos usuários Discord precisam de `make admin-link` pelo operador; implementar redeem via DM no bot elimina essa fricção
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite; restart do servidor cancela watchers em curso
- **Próximo CRD: `Cluster`** — seguir padrão: `wasp/resources/cluster/{manifest,provisioner,inventory}.py` + `@tool` em `wasp/provision.py`
- **Bidirecionalidade `watcher.py` ↔ `resources/`** — `extract_channel/extract_chat_id` vivem em `watcher.py` mas são importados por `resources/platform/`. Quando um terceiro CRD chegar, mover para módulo folha (ex: `wasp/session.py`)
- **Status check manual** — tool para consultar estado de uma Platform sem depender do watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — papéis (admin, operator, viewer)
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`
- **Falha clara em configuração ausente** — validar variáveis obrigatórias no startup

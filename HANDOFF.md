# Handoff

## Why

Bootstrap específico de canal (Telegram, Discord) vaza para três sítios — `main.py::create_app()` (lifespan inline do Discord), `wasp/clients/interfaces.py` (APIs assimétricas `build()`/`build_discord()` + singleton `discord_pkg._notifier`), `wasp/watcher.py::_select_notifier` (ifs hardcoded por kind). Adicionar Google Chat ou outro canal exige editar os três.

Abordagem aprovada: `Channel` Protocol por canal (`enabled()`, `build_interface()`, `lifespan()`, `notifier()`); registry global em `wasp/clients/channels.py`; `ChannelLoader` único ponto que `main.py` conhece (`channel_loader.build_app()`). Canais se auto-registram no import do package. Spec completo em `docs/sdlc/02-design/2026-05-28-channel-loader-design.md` (commit `598f1ed`).

Alternativas rejeitadas:
- Escopo apenas main.py+loader (deixaria `watcher._select_notifier` com ifs hardcoded — não cumpriria o objetivo de "evoluir próximos canais da mesma maneira").
- API granular `build_interfaces() + iter_lifespans()` em main.py (mantém boilerplate).
- Hooks `register(loader)` invertidos (dispersa o que cada canal faz).
- Singleton de módulo `active_loader` ou parâmetro `notifier_resolver` no watcher (preferido auto-registro via registry global).
- Promover `local` a `Channel` (não tem token nem interface; permanece resolvido por fallback explícito em `_select_notifier`).

**Entregue nesta sessão (branch `dev`, aguardando merge):**
- Discord bot completo com feature parity ao Telegram: `wasp/clients/discord/` (`bot.py`, `notifier.py`, `__init__.py`)
- `DiscordBot(discord.Client)` com `on_message` (auth guard + per-user session) e `on_ready` (registra o event loop para bridge cross-loop)
- `DiscordNotifier` com `set_loop()` — bridge via `asyncio.run_coroutine_threadsafe` para enviar notificações do watcher thread para o loop do Discord
- `InterfaceLoader.build_discord()` com singleton `discord_pkg._notifier`
- Lifespan do Discord integrado ao FastAPI via `asynccontextmanager` wrapping do lifespan do agno
- Routing `"dc"` em `_select_notifier`, `extract_channel`, `extract_chat_id`
- `make admin-link USER_ID=<uid> CHANNEL=dc ID=<id>` — vincula canal adicional a usuário existente
- `auth_cli link` subcomando + `scripts/admin-link` + target no Makefile
- `docs/runbooks/auth-admin.md` atualizado com seção "Vincular canal adicional"
- `docs/runbooks/discord-setup.md` — setup inicial, obtenção de user ID, bootstrap, convite de usuários
- Smoke test manual: bot respondendo, provisioning + notificação watcher funcionando via Discord
- 261 testes passando, 100% coverage
## In Progress

Spec aprovado e commitado em `dev`. Próximo passo: gerar plano de implementação invocando `superpowers:writing-plans` com o spec como entrada. Implementação ainda **não** iniciada.

## Open Questions / Hypotheses

- Nenhuma. Decisões de design fechadas no spec.

## Known Broken

### Implementados (aguardando marcação após merge)
- `docs/sdlc/02-design/archived/2026-05-27-discord-bot-design.md` — Discord Bot Design
- `docs/sdlc/03-execution/archived/2026-05-27-discord-bot-plan.md` — Discord Bot Implementation Plan
- `docs/sdlc/02-design/archived/2026-05-26-resources-package-design.md` — Resources Package Design
- `docs/sdlc/02-design/archived/2026-05-26-interface-loader-design.md` — InterfaceLoader Design

### Status: Idea (exploração — backlog de features)
- `docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md` — Discord Slash Commands
- `docs/sdlc/01-exploration/2026-05-26-opentelemetry-tracing.md` — Distributed Tracing
- `docs/sdlc/01-exploration/2026-05-20-llm-behavior-evaluation.md` — golden set para regressões no system prompt
- `docs/sdlc/01-exploration/2026-05-20-token-cost-budget.md` — alertas de orçamento
- `docs/sdlc/01-exploration/2026-05-21-cli-device-flow-oauth.md` — auth OAuth device flow
- `docs/sdlc/01-exploration/2026-05-21-auth-cognito-federation.md` — auth Cognito federation
- 14 explorações de 2026-05-26 em `docs/sdlc/01-exploration/`: helm-chart, dora-metrics, rate-limiting, prompt-versioning, load-testing, sbom, supply-chain-security, secret-rotation, code-quality-security-scanning, penetration-test, eu-ai-act, privacy-data-retention, disaster-recovery, incident-response
- Nada quebrado. Branch `dev` segue passando em `make test` (261 tests, 100% coverage). Spec é só documentação.

## How to Resume

```
cat docs/sdlc/02-design/2026-05-28-channel-loader-design.md
```

Depois invoque `/superpowers:writing-plans` referenciando o spec acima.

## Next Steps

1. **Merge `dev` → `main`** — branch passou em `make test` (261 tests), smoke test Discord confirmado
2. **Atualizar status dos specs entregues** — mover specs/plans Discord + resources + interface-loader para `archived/` ou marcar `Implemented`
3. **Decidir próxima feature** — sugestões em ordem de valor imediato:
   - `01-exploration/2026-05-27-discord-slash-commands.md` — ergonomia para usuários Discord
   - `01-exploration/2026-05-20-llm-behavior-evaluation.md` — previne regressões silenciosas no system prompt
   - `01-exploration/2026-05-26-opentelemetry-tracing.md` — observabilidade end-to-end
1. Invocar `superpowers:writing-plans` para gerar plano de implementação a partir de `docs/sdlc/02-design/2026-05-28-channel-loader-design.md`.
2. Executar plano (criar `wasp/clients/channels.py`, `wasp/clients/telegram/channel.py`, `wasp/clients/discord/channel.py`; refatorar `main.py` e `wasp/watcher.py`; deletar `wasp/clients/interfaces.py` e `discord_pkg._notifier`).
3. Validar: `make format`, `make test`, `make e2e-with-debug`.
4. Marcar spec como `Implemented` após merge.

## Backlog (carry-over)

- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`) — `/provision`, `/list`, `/status` como alternativa à linguagem natural
- **Handler de convite via DM no Discord** — hoje novos usuários Discord exigem `make admin-link` pelo operador; implementar redeem de token por DM elimina essa fricção (ver `wasp/clients/telegram/webhook.py` como referência)
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`) — persistir `platform_watches` em SQLite; restart do servidor cancela watchers em curso
- **Próximo CRD: `Cluster`** — seguir padrão: `wasp/resources/cluster/{manifest,provisioner,inventory}.py` + `@tool` em `wasp/provision.py`
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** — hoje vivem em `watcher.py` mas são importados por `resources/platform/`; quando um terceiro CRD chegar, mover para ex: `wasp/session.py`
- **Status check manual** — tool para consultar estado de uma Platform sem depender do watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — papéis (admin, operator, viewer)
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`
- **Falha clara em configuração ausente** — validar variáveis obrigatórias no startup

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

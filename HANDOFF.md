# Handoff

## Why

Channel-specific bootstrap was leaking across `main.py`, `wasp/clients/interfaces.py` e `wasp/watcher.py`. Cada novo canal (Telegram, Discord, Google Chat…) exigia editar três sítios.

Solução entregue (commits `29811b4`..`51b20ca` no branch `dev`):

- `wasp/clients/channels.py` — `Channel` Protocol + global registry (`register/get/iter_channels/reset`) + `ChannelLoader.build_app()` que compõe interfaces e lifespans via `AsyncExitStack`.
- `wasp/clients/telegram/channel.py` — `TelegramChannel` (auto-registra no import do package).
- `wasp/clients/discord/channel.py` — `DiscordChannel` (auto-registra; lifespan inline que sobe e fecha o bot).
- `main.py::create_app()` reduzido a 3 linhas: `ChannelLoader(agent).build_app()`.
- `wasp/watcher.py::_select_notifier` resolve via `channels.get(target).notifier()`.
- `wasp/clients/interfaces.py` e o singleton `discord_pkg._notifier` deletados.

Adicionar Google Chat agora: criar `wasp/clients/google_chat/{__init__.py, channel.py}` + uma linha `import wasp.clients.google_chat` em `main.py`. Zero edições centrais.

**Validação:** 290 testes unit + 1 e2e, 100% cov, ruff clean.

## Implementados (aguardando marcação após merge)

- `docs/sdlc/02-design/archived/2026-05-28-channel-loader-design.md`
- `docs/sdlc/03-execution/archived/2026-05-28-channel-loader.md`
- `docs/sdlc/02-design/archived/2026-05-27-discord-bot-design.md`
- `docs/sdlc/03-execution/archived/2026-05-27-discord-bot-plan.md`
- `docs/sdlc/02-design/archived/2026-05-26-resources-package-design.md`
- `docs/sdlc/02-design/archived/2026-05-26-interface-loader-design.md`

## Next Steps

1. **Merge `dev` → `main`.**
2. **Escolher próxima feature** — sugestões em ordem de valor:
   - `01-exploration/2026-05-27-discord-slash-commands.md` — ergonomia para usuários Discord
   - `01-exploration/2026-05-20-llm-behavior-evaluation.md` — previne regressões silenciosas no system prompt
   - `01-exploration/2026-05-26-opentelemetry-tracing.md` — observabilidade end-to-end

## Backlog (carry-over)

- **Discord slash commands** (`01-exploration/2026-05-27-discord-slash-commands.md`) — `/provision`, `/list`, `/status` como alternativa à linguagem natural
- **Handler de convite via DM no Discord** — hoje novos usuários Discord exigem `make admin-link` pelo operador; implementar redeem de token por DM elimina essa fricção (ver `wasp/clients/telegram/webhook.py` como referência)
- **Restart resilience do watcher** (`02-design/2026-05-16-platform-watcher-restart-resilience.md`) — persistir `platform_watches` em SQLite; restart do servidor cancela watchers em curso
- **Próximo CRD: `Cluster`** — seguir padrão: `wasp/resources/cluster/{manifest,provisioner,inventory}.py` + `@tool` em `wasp/provision.py`
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** — hoje vivem em `watcher.py` mas são importados por `resources/platform/`; quando um terceiro CRD chegar, mover para ex.: `wasp/session.py`
- **Status check manual** — tool para consultar estado de uma Platform sem depender do watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — papéis (admin, operator, viewer)
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`
- **Falha clara em configuração ausente** — validar variáveis obrigatórias no startup

## Known Broken

Nada. Branch `dev` passa em `make test` (290 testes, 100% cov), `make e2e-with-debug`, `ruff check .`.

## Idea-stage explorations

- `01-exploration/2026-05-27-discord-slash-commands.md`
- `01-exploration/2026-05-26-opentelemetry-tracing.md`
- `01-exploration/2026-05-20-llm-behavior-evaluation.md`
- `01-exploration/2026-05-20-token-cost-budget.md`
- `01-exploration/2026-05-21-cli-device-flow-oauth.md`
- `01-exploration/2026-05-21-auth-cognito-federation.md`
- 14 explorações de 2026-05-26 em `01-exploration/`: helm-chart, dora-metrics, rate-limiting, prompt-versioning, load-testing, sbom, supply-chain-security, secret-rotation, code-quality-security-scanning, penetration-test, eu-ai-act, privacy-data-retention, disaster-recovery, incident-response

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

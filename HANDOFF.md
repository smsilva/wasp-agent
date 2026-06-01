# Handoff

## Why

**Extensibilidade de recursos (v1) — IMPLEMENTADA** na branch `dev`. Adicionar novos Custom Resources não exige mais editar `agent.py`/`provision.py`: cada recurso expõe um `ResourceProvider` (Protocol) registrado na lista `PROVIDERS` de `wasp/resources/registry.py`; `agent.py` monta `tools=ResourceRegistry.discover().all_tools()`. Loaders de CRD (filesystem/git/cluster) adiados para v2+.

## In Progress

Nada em andamento.

## Open Questions / Hypotheses

- Prefixo geral `WASP_AGENT_*` — decisão pendente (`docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`). Opções: `WASP_*`, `WAGENT_*`, manter, ou outro.
- `_now()` duplicado entre `wasp/auth/_connection.py` (sqlite) e `postgres_repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.

## Next Steps

1. **Renomeação do prefixo `WASP_AGENT_*`** — quando o nome novo for decidido.
2. **Refinar `PostgresAuthRepository`** (opcional) — migrar timestamps para `TIMESTAMPTZ` e `user_id` para `UUID` se houver motivação.
3. **`readOnlyRootFilesystem`** — habilitar no Helm chart condicionado a `DATABASE_BACKEND=postgres`; ver avaliação em `docs/sdlc/02-design/archived/2026-05-30-dockerfile-hardening.md`.

## Backlog (carry-over)

- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`)
- **Handler de convite via DM no Discord** — ver `wasp/clients/telegram/webhook.py` como referência
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`)
- **Próximo CRD: `Cluster`** — padrão `wasp/resources/cluster/{manifest,provisioner,inventory,provider}.py` + linha em `PROVIDERS` (`wasp/resources/registry.py`); não editar `agent.py`
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** quando terceiro CRD chegar
- **Status check manual** — tool para consultar Platform sem watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — admin, operator, viewer
- **Testcontainers no E2E** — avaliar substituir setup manual k3d/Gitea
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução
- **Postgres no agno em produção** — basta `DATABASE_BACKEND=postgres` + `DATABASE_URL` (sessions e auth já funcionais).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

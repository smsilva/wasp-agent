# Handoff

## Why

Preparar PostgreSQL como backend real de auth. `wasp/auth/postgres_repository.py` implementa o `AuthRepository` Protocol; `get_repository()` instancia direto quando `DATABASE_BACKEND=postgres` (lê `DATABASE_URL`). Testes reais rodam contra Postgres em container via **testcontainers**, dentro do `make test`.

Decisões: (1) timestamps TEXT ISO + `user_id` TEXT hex — paridade exata com o sqlite, SQL difere só por `?`→`%s`, menos risco. `TIMESTAMPTZ`/`UUID` nativos rejeitados por ora (mais código, mais divergência). (2) Concorrência via `SELECT ... FOR UPDATE` (`redeem_invite`) e `LOCK TABLE auth_users IN ACCESS EXCLUSIVE MODE` (`bootstrap_admin`) — equivalentes Postgres do `BEGIN IMMEDIATE`. (3) Testes postgres correm no `make test` (Docker obrigatório), não gated — escolha explícita sobre `make test-postgres` separado ou `omit` de coverage.

## In Progress

Nada aberto. `PostgresAuthRepository` completo via TDD (21 testes em `test_postgres_auth_repository.py` + esqueleto em `test_postgres_skeleton.py`). Validação completa verde: `make format`, `make test` (325 passed, 1 skipped, 100% coverage), `make e2e-with-debug` (1 passed, 37s).

## Open Questions / Hypotheses

- Prefixo geral `WASP_AGENT_*` — decisão pendente (`docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`). Opções: `WASP_*`, `WAGENT_*`, manter, ou outro.
- Compartilhar Postgres entre auth e sessions agno via `DATABASE_URL` único, ou separar? Spec assume único.
- `_now()` duplicado entre `wasp/auth/_connection.py` (sqlite) e `postgres_repository.py`. Intencional por enquanto (1 linha); extrair só se surgir terceiro caller.

## Known Broken

- `claude-sonnet-4-5-20250929` no proxy CIandT está sem deployment saudável — *unexpected*. Default em `anthropic.claude-4-6-sonnet`. Se cair, conferir `~/.credentials/bash_flow`.

## How to Resume

`git status && git log -10 --oneline`

Rodar testes Postgres isolados: `uv run pytest -m postgres --no-cov -v` (precisa de Docker).

## Next Steps

1. **Dockerfile / docker-compose** — service Postgres opcional, remover assunção de SQLite no Dockerfile, volumes persistentes (`docs/references/production-readiness-checklist.md:127`).
2. **Renomeação do prefixo `WASP_AGENT_*`** — quando o nome novo for decidido.
3. **Refinar `PostgresAuthRepository`** (opcional) — migrar timestamps para `TIMESTAMPTZ` e `user_id` para `UUID` se houver motivação.

## Backlog (carry-over)

- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`)
- **Handler de convite via DM no Discord** — ver `wasp/clients/telegram/webhook.py` como referência
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`)
- **Próximo CRD: `Cluster`** — padrão `wasp/resources/cluster/{manifest,provisioner,inventory}.py`
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** quando terceiro CRD chegar
- **Status check manual** — tool para consultar Platform sem watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — admin, operator, viewer
- **Testcontainers no E2E** — avaliar substituir setup manual k3d/Gitea (agora há precedente de testcontainers no repo)
- **Falha clara em configuração ausente** — validar env obrigatórias no startup
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução
- **Postgres no agno em produção** — basta `DATABASE_BACKEND=postgres` + `DATABASE_URL` (sessions e auth já funcionais).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

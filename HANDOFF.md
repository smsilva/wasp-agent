# Handoff

## Why

Adicionar Postgres como serviço de infra local no docker-compose. Backend já estava funcional (`PostgresAuthRepository` + agno sessions via `DATABASE_URL`); faltava o compose, os make targets, e o runbook. Decisões: banco único (`wasp_agent`) para auth e sessions; compose de infra-only (app roda fora via `make run`); credenciais via `.env`; `docker compose down postgres` (escopo mínimo) não `docker compose down` (derrubaria Jaeger também).

## In Progress

Implementação concluída e validada: `docker-compose.yml`, `.env.example`, `Makefile` (postgres-up/postgres-down), `docs/runbooks/local-infra.md`. Próximo: decidir se faz merge para `main` ou abre PR.

Branch atual: `dev`. Aguardando escolha do usuário (merge local / PR / manter / descartar).

## Open Questions / Hypotheses

- Prefixo geral `WASP_AGENT_*` — decisão pendente (`docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`). Opções: `WASP_*`, `WAGENT_*`, manter, ou outro.
- `_now()` duplicado entre `wasp/auth/_connection.py` (sqlite) e `postgres_repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.

## Known Broken

- `claude-sonnet-4-5-20250929` no proxy CIandT está sem deployment saudável — *unexpected*. Default em `anthropic.claude-4-6-sonnet`. Se cair, conferir `~/.credentials/bash_flow`.

## How to Resume

```bash
git status && git log -10 --oneline
```

Validar infra local:
```bash
make postgres-up
docker compose ps   # aguardar healthy
make postgres-down
```

## Next Steps

1. **Merge ou PR** — branch `dev` tem o compose pronto; escolha pendente do usuário.
2. **Dockerfile hardening** — draft em `docs/sdlc/02-design/2026-05-30-dockerfile-hardening.md` (usuário não-root, `.dockerignore`, alpine/distroless). Implementar após merge.
3. **Renomeação do prefixo `WASP_AGENT_*`** — quando o nome novo for decidido.
4. **Refinar `PostgresAuthRepository`** (opcional) — migrar timestamps para `TIMESTAMPTZ` e `user_id` para `UUID` se houver motivação.

## Backlog (carry-over)

- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`)
- **Handler de convite via DM no Discord** — ver `wasp/clients/telegram/webhook.py` como referência
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`)
- **Próximo CRD: `Cluster`** — padrão `wasp/resources/cluster/{manifest,provisioner,inventory}.py`
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** quando terceiro CRD chegar
- **Status check manual** — tool para consultar Platform sem watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — admin, operator, viewer
- **Testcontainers no E2E** — avaliar substituir setup manual k3d/Gitea
- **Falha clara em configuração ausente** — validar env obrigatórias no startup
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução
- **Postgres no agno em produção** — basta `DATABASE_BACKEND=postgres` + `DATABASE_URL` (sessions e auth já funcionais).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

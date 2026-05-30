# Handoff

## Why

Preparar o código para PostgreSQL sem implementar o backend. Removeu hardcodes (`SqliteDb(db_file="agent.db", ...)` em `wasp/agent.py`), abstraiu sessões agno num builder `wasp/sessions.py::build_session_db()` simétrico a `wasp/models.py::build_model()`, e adicionou branches `elif backend == "postgres"` em `get_repository()` e `build_session_db()`. Renomeou `WASP_AGENT_DB_{BACKEND,FILE}` → `DATABASE_{BACKEND,FILE}` para alinhar com a convenção universal `DATABASE_URL` — formalizado como exceção ao prefixo `WASP_AGENT_*` no `CLAUDE.md`.

Alternativas rejeitadas: (1) implementar PostgresAuthRepository agora — fora do escopo; (2) apenas externalizar env var sem branch postgres — perderia o slot visível; (3) aliasing temporário de env vars antigas → novas — código permanente para ganho marginal.

Descoberta tardia: `agno.db.postgres` JÁ está presente no pacote agno. O branch postgres de sessions é funcional em produção quando `DATABASE_URL` está setado. Apenas o branch postgres de **auth** permanece como slot (`NotImplementedError`) aguardando `wasp/auth/postgres_repository.py`.

## In Progress

Nada. Spec marcado `Implemented`. Branch `dev` ahead de `origin/dev` em 9 commits, com `make format`/`make test`/`make cc`/`make e2e-with-debug` todos verdes.

## Open Questions / Hypotheses

- Prefixo geral `WASP_AGENT_*` — decisão pendente (`docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`). Opções: `WASP_*`, `WAGENT_*`, manter, ou outro.
- Compartilhar Postgres entre auth e sessions agno via `DATABASE_URL` único, ou separar? Spec assume único; revisar quando `PostgresAuthRepository` for implementado.

## Known Broken

- `claude-sonnet-4-5-20250929` no proxy CIandT (`flow.ciandt.com/flow-llm-proxy`) está sem deployment saudável — *unexpected*. Default trocado para `anthropic.claude-4-6-sonnet`. Se este também cair, conferir `~/.credentials/bash_flow` para modelos atualmente disponíveis.

## How to Resume

`git status && git log -10 --oneline`

Se for retomar trabalho de Postgres: ler `docs/sdlc/02-design/2026-05-30-postgres-readiness.md` §12 (próximos specs).

## Next Steps

Selecionar item do Backlog conforme prioridade. Sequência natural pós este spec:

1. **PostgresAuthRepository** — implementar `wasp/auth/postgres_repository.py`. Protocol pronto, singleton exercitado, branch slot já em `get_repository()`. Precisa definir contrato do construtor (lê `DATABASE_URL`), DDL Postgres (`TIMESTAMPTZ`, `UUID`), substituir `BEGIN IMMEDIATE` por `SELECT FOR UPDATE` ou serializable tx.
2. **Dockerfile / docker-compose** — adicionar service Postgres opcional, remover assunção de SQLite no Dockerfile, definir volumes persistentes (ver `docs/references/production-readiness-checklist.md:127`).
3. **Renomeação geral do prefixo `WASP_AGENT_*`** — quando o nome novo for decidido (ver exploration doc).

## Backlog (carry-over)

- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`)
- **Handler de convite via DM no Discord** — ver `wasp/clients/telegram/webhook.py` como referência
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`)
- **Próximo CRD: `Cluster`** — padrão `wasp/resources/cluster/{manifest,provisioner,inventory}.py`
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** (ex: `wasp/session.py`) quando terceiro CRD chegar
- **Status check manual** — tool para consultar Platform sem watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — admin, operator, viewer
- **Testcontainers** — avaliar substituir setup manual k3d/Gitea no E2E
- **Falha clara em configuração ausente** — validar env obrigatórias no startup
- **PostgresAuthRepository** — implementar quando migração for priorizada (Protocol já pronto, singleton já exercitado pelos callers, branch slot já em `get_repository()`)
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução
- **Postgres no agno em produção** — não precisa de spec novo; basta setar `DATABASE_BACKEND=postgres` + `DATABASE_URL` (sessions já funcional).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

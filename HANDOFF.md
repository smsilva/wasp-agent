# Handoff

## Why

Tornar `GITOPS_REPO` e `GITHUB_BASE_URL` variáveis obrigatórias em `GitOpsCommitter.from_env()`, eliminando os defaults hardcoded (`smsilva/wasp-gitops` e `https://api.github.com`). Motivação: defaults com dados pessoais do autor eram um risco silencioso — qualquer deploy sem `.env` configurado apontaria para o repo errado. Padrão escolhido: `ValueError` explícito (igual a `GH_PAT`), fail-fast no startup via `probe()`.

## In Progress

Implementação concluída: `gitops_committer.py` atualizado, `.env.example` com as vars descomentadas, testes em `test_gitops_committer.py` e `test_provision.py` atualizados (326 passed, 1 skipped). Próximo: decidir merge para `main` ou abrir PR.

Branch atual: `dev`. Aguardando escolha do usuário.

## Open Questions / Hypotheses

- Prefixo geral `WASP_AGENT_*` — decisão pendente (`docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`). Opções: `WASP_*`, `WAGENT_*`, manter, ou outro.
- `_now()` duplicado entre `wasp/auth/_connection.py` (sqlite) e `postgres_repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.

## Known Broken

- `claude-sonnet-4-5-20250929` no proxy CIandT está sem deployment saudável — *unexpected*. Default em `anthropic.claude-4-6-sonnet`. Se cair, conferir `~/.credentials/bash_flow`.

## How to Resume

```bash
git status && git log -10 --oneline
uv run pytest -x -q
```

## Next Steps

1. **Merge ou PR** — branch `dev` com as mudanças prontas; escolha pendente do usuário.
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
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução
- **Postgres no agno em produção** — basta `DATABASE_BACKEND=postgres` + `DATABASE_URL` (sessions e auth já funcionais).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

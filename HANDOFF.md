# Handoff

## Why

Sessão de brainstorming + planejamento da **extensibilidade de recursos** do wasp-agent: permitir adicionar novos Custom Resources sem editar `agent.py`/`provision.py`, via contrato `ResourceProvider` (Protocol) descoberto por `ResourceRegistry.discover()` sobre plugin discovery do Python. Escopo v1 decidido: opção A (mínima) + packaging in-tree. Loaders de CRD (filesystem/git/cluster) adiados para v2+.

## In Progress

Spec e plano escritos e commitados:
- Spec: `docs/sdlc/02-design/2026-05-31-resource-provider-extensibility.md` (Status: Approved)
- Plano: `docs/sdlc/03-execution/2026-05-31-resource-provider-extensibility.md` (7 tasks, TDD)

**Próximo a ser implementado:** executar o plano de extensibilidade (Tasks 1-7). Usar `superpowers:subagent-driven-development` ou `superpowers:executing-plans`. Nada de código implementado ainda — só design + plano.

Decisão consciente registrada na spec: no v1, adicionar recurso = nova imagem + `kubectl rollout restart` (descoberta de providers no boot). Trade-off aceitável; descoberta dinâmica sem restart é motivação dos loaders de CRD em v2+.

Branch atual: `dev`.

## Open Questions / Hypotheses

- Prefixo geral `WASP_AGENT_*` — decisão pendente (`docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`). Opções: `WASP_*`, `WAGENT_*`, manter, ou outro.
- `_now()` duplicado entre `wasp/auth/_connection.py` (sqlite) e `postgres_repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.

## Next Steps

1. **Implementar extensibilidade de recursos (v1)** — executar `docs/sdlc/03-execution/2026-05-31-resource-provider-extensibility.md`. É o próximo trabalho de código.
2. **Dockerfile hardening** — draft em `docs/sdlc/02-design/2026-05-30-dockerfile-hardening.md` (usuário não-root, `.dockerignore`, alpine/distroless).
3. **Renomeação do prefixo `WASP_AGENT_*`** — quando o nome novo for decidido.
4. **Refinar `PostgresAuthRepository`** (opcional) — migrar timestamps para `TIMESTAMPTZ` e `user_id` para `UUID` se houver motivação.

## Backlog (carry-over)

- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`)
- **Handler de convite via DM no Discord** — ver `wasp/clients/telegram/webhook.py` como referência
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`)
- **Próximo CRD: `Cluster`** — padrão `wasp/resources/cluster/{manifest,provisioner,inventory}.py` (+ `provider.py` após a extensibilidade v1)
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** quando terceiro CRD chegar
- **Status check manual** — tool para consultar Platform sem watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — admin, operator, viewer
- **Testcontainers no E2E** — avaliar substituir setup manual k3d/Gitea
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução
- **Postgres no agno em produção** — basta `DATABASE_BACKEND=postgres` + `DATABASE_URL` (sessions e auth já funcionais).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

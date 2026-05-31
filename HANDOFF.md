# Handoff

## Why

**Extensibilidade de recursos (v1) — IMPLEMENTADA** na branch `dev`. Adicionar novos Custom Resources não exige mais editar `agent.py`/`provision.py`: cada recurso expõe um `ResourceProvider` (Protocol) registrado na lista `PROVIDERS` de `wasp/resources/registry.py`; `agent.py` monta `tools=ResourceRegistry.discover().all_tools()`. Loaders de CRD (filesystem/git/cluster) adiados para v2+.

## In Progress

Nada em andamento. A extensibilidade v1 foi concluída (Tasks 1-7, e2e verde).

**Para fechar o ciclo:** branch `dev` ainda não mergeada em `main`. Ao mergear, arquivar a spec/plano (`docs/sdlc/0{2,3}-*/2026-05-31-resource-provider-extensibility.md`) — design+execução arquivam quando a implementação chega em `main`.

**Decisão-chave (2026-05-31):** o discovery NÃO usa `importlib.metadata.entry_points`. O projeto não é pacote instalável (sem `[build-system]`), então entry points retornariam `[]`. Mecanismo: lista in-tree `PROVIDERS` resolvida via `importlib.import_module`, que funciona na árvore de fontes em todo lugar (local/test/e2e/Docker). Spec/plano revisados refletem isso. Decisão consciente registrada na spec: adicionar recurso = nova imagem + `kubectl rollout restart` (discovery no boot); descoberta dinâmica sem restart é motivação dos loaders de CRD em v2+.

Branch atual: `dev`.

## Open Questions / Hypotheses

- Prefixo geral `WASP_AGENT_*` — decisão pendente (`docs/sdlc/01-exploration/2026-05-30-env-var-prefix-naming.md`). Opções: `WASP_*`, `WAGENT_*`, manter, ou outro.
- `_now()` duplicado entre `wasp/auth/_connection.py` (sqlite) e `postgres_repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.

## Next Steps

1. **Dockerfile hardening** — draft em `docs/sdlc/02-design/2026-05-30-dockerfile-hardening.md` (usuário não-root, `.dockerignore`, alpine/distroless).
2. **Renomeação do prefixo `WASP_AGENT_*`** — quando o nome novo for decidido.
3. **Refinar `PostgresAuthRepository`** (opcional) — migrar timestamps para `TIMESTAMPTZ` e `user_id` para `UUID` se houver motivação.

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

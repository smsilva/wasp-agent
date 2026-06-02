# Handoff

## Why

**Extensibilidade de recursos (v1) — concluída.** Novos CRDs não exigem editar `agent.py`/`provision.py`: cada recurso expõe um `ResourceProvider` (Protocol) registrado em `PROVIDERS` de `wasp/resources/registry.py`; `agent.py` monta `tools=ResourceRegistry.discover().all_tools()`. Discovery in-tree via `importlib.import_module` — não usa `importlib.metadata.entry_points` (projeto não é pacote instalável). Loaders de CRD v2+ adiados.

**Dockerfile hardening — concluído.** Base trocada para `python:3.14-alpine`; usuário não-root `appuser`; `.dockerignore` criado. `readOnlyRootFilesystem` avaliado: viável apenas com `DATABASE_BACKEND=postgres` (SQLite escreve `agent.db` em `/app`).

**`get_platform_status` tool — concluída.** Nova tool `get_platform_status(name)` em `provision.py` para consultar status de uma Platform específica sem watcher. Retorna `{"status", "name", "message"}` com mensagem user-friendly ("A Platform acme está Ready desde 30/05."). `KubernetesResourceReader` ganhou `get_by_name` (usa `get_cluster_custom_object`, retorna `None` em 404 via `getattr(e, "status", None) == 404`). `PlatformInventory.get` segue o mesmo padrão de auth guard do `list`. 352 testes, 100% coverage.

**Renomeação de prefixo env vars — concluída.** `WASP_AGENT_*` → `AGENT_*` em toda a codebase. Motivação: o agente roda em container isolado com ConfigMap próprio, tornando `AGENT_` sem ambiguidade. Variáveis renomeadas: `AGENT_NOTIFIER`, `AGENT_INVITE_TTL_HOURS`, `AGENT_URL`, `AGENT_ID`. Docs históricos/archived mantidos com nomes antigos intencionalmente.

## In Progress

Nada em andamento.

## Open Questions / Hypotheses

- `_now()` duplicado entre `wasp/auth/_connection.py` (sqlite) e `postgres_repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.
- OTLP 401 pós-`make test` é ruído cosmético: thread background do exporter dispara depois que pytest encerra, tenta logar mas stdout já fechou. Não afeta exit code. Pré-existente, depende de `OTEL_EXPORTER_OTLP_ENDPOINT` estar setado no shell.

## How to Resume

```bash
make format && make test
```

Próxima ação: escolher item do backlog.

## Next Steps

1. **`readOnlyRootFilesystem`** — habilitar no Helm chart condicionado a `DATABASE_BACKEND=postgres`; ver avaliação em `docs/sdlc/02-design/archived/2026-05-30-dockerfile-hardening.md`.
2. **Refinar `PostgresAuthRepository`** (opcional) — migrar timestamps para `TIMESTAMPTZ` e `user_id` para `UUID` se houver motivação.

## Backlog (carry-over)

- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`)
- **Handler de convite via DM no Discord** — ver `wasp/clients/telegram/webhook.py` como referência
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`)
- **Próximo CRD: `Cluster`** — padrão `wasp/resources/cluster/{manifest,provisioner,inventory,provider}.py` + linha em `PROVIDERS` (`wasp/resources/registry.py`); não editar `agent.py`
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** quando terceiro CRD chegar
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — admin, operator, viewer
- **Testcontainers no E2E** — avaliar substituir setup manual k3d/Gitea
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução
- **Postgres no agno em produção** — basta `DATABASE_BACKEND=postgres` + `DATABASE_URL` (sessions e auth já funcionais)

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

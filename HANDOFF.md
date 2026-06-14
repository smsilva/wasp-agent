# Handoff

## Why

Jira Coding Agent v2 — implementação real (`claude-code-action` + App "Claude"). O agente lê a issue, implementa, abre PR, comenta no Jira e transiciona pra "In Review".

Spec: `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md` (Status: Implemented). Plano: `docs/sdlc/03-execution/2026-06-13-jira-coding-agent-v2.md`. Setup: `docs/runbooks/jira-coding-agent-setup.md`.

**Validado end-to-end em 2026-06-13** (run `27483606376`, PR `#9`, PLTF-11). Setup live, não recriar:
- Site `smsilva.atlassian.net`, projeto `PLTF`. Issue de teste: **PLTF-11** (Story; criada espelhando PLTF-2). Mantém 1 comentário do último run validado.
- Automation rule ativa no PLTF: nome "Jira Coding Agent — manual trigger", trigger "Manual trigger from work item", action "Send web request" → `POST https://api.github.com/repos/smsilva/wasp-agent/dispatches`, body `event_type=jira-trigger-event` + `client_payload.issue_key={{issue.key}}`. Disparar via issue → menu `• • •` → Automation.
- PAT fine-grained do GitHub chamado "jira" (escopo `smsilva/wasp-agent`, `Contents: write` + `Actions: write`) cola no header `Authorization: Bearer <PAT>` da rule.
- Secrets no repo GitHub: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`. Valores também no `.env` local.
- Config Jira em `.jira/config.md` (gitignored). Permissões read-only do Atlassian MCP + hook de validação de task file em `.claude/settings.local.json`.

Atlassian MCP não está no catálogo `mcp --list`; conectar via `/mcp` (claude mcp add http `https://mcp.atlassian.com/v1/mcp`) antes de usar `mcp__atlassian__*`. Deletar comentário Jira não tem tool MCP — usar REST `DELETE /rest/api/3/issue/{key}/comment/{id}` com basic auth do `.env`.

## In Progress

Nada em andamento. v2 entregue e validado.

Próximo: v3 (ver Backlog) — gate de ambiguidade, `pr-agent.yaml`, dry-run, CLI Python testado. SEC-008 (artefato de log) pendente.

## Open Questions / Hypotheses

Nenhuma.

## Known Broken

Nenhum.

## How to Resume

```bash
make test 2>&1 | tail -5
```

Confirmar suite verde + 100% coverage.

## Next Steps

Nenhum item priorizado. Ver Backlog.

## Backlog (carry-over)

- **`_now()` duplicado** em `wasp/auth/repository.py` e `wasp/watches/repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.
- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`)
- **Handler de convite via DM no Discord** — ver `wasp/clients/telegram/webhook.py` como referência
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** quando terceiro CRD chegar
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — admin, operator, viewer
- **Testcontainers no E2E** — avaliar substituir setup manual k3d/Gitea
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução
- **Postgres no agno em produção** — basta `DATABASE_BACKEND=postgres` + `DATABASE_URL`
- **`readOnlyRootFilesystem`** — habilitar condicionado a `DATABASE_BACKEND=postgres`
- **Mensageria para watches** (`docs/sdlc/01-exploration/2026-06-03-mensageria-watcher.md`) — Redis Streams como evolução quando replicas > 1
- **Jira Coding Agent v3** — gate de ambiguidade, `pr-agent.yaml` (auto-fix de CI via action oficial), dry-run, extração para CLI Python testado. Resolver SEC-008 (apertar `if: failure()` + `retention-days: 7` no artifact de log).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

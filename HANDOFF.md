# Handoff

## Why

Jira Coding Agent v2 entregue: agente lê issue do Jira, implementa, abre PR, comenta no Jira e transiciona pra "In Review". Implementação real via `claude-code-action` + App "Claude". Alternativa rejeitada: `claude -p` headless cru (mais cola para auth/PR; substituído pela action que cunha o token internamente a partir do `CLAUDE_CODE_OAUTH_TOKEN`).

Spec: `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md` (Status: Implemented). Plano: `docs/sdlc/03-execution/2026-06-13-jira-coding-agent-v2.md`. Setup: `docs/runbooks/jira-coding-agent-setup.md`.

**Validado end-to-end em 2026-06-13** com PLTF-11. Setup live, não recriar:
- Site `smsilva.atlassian.net`, projeto `PLTF`. Issue de teste: **PLTF-11** (Story; criada espelhando PLTF-2).
- Automation rule ativa: "Jira Coding Agent — manual trigger", `POST https://api.github.com/repos/smsilva/wasp-agent/dispatches`, body `event_type=jira-trigger-event` + `client_payload.issue_key={{issue.key}}`. Disparar via issue → menu `• • •` → Automation.
- PAT fine-grained "jira" (escopo `smsilva/wasp-agent`, `Contents: write` + `Actions: write`) no header `Authorization: Bearer <PAT>` da rule (fica no Jira, não no GitHub).
- Secrets no repo: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`. Valores Jira também no `.env` local.
- Settings → Actions → General: flag "Allow GitHub Actions to create and approve pull requests" precisa estar ligada (sem ela, `gh pr create` falha com GraphQL `createPullRequest`).
- Primeiro PR de cada novo branch do bot exige aprovação manual ("Approve workflows to run").

Atlassian MCP não está no catálogo `mcp --list`; conectar via `/mcp` (`claude mcp add http https://mcp.atlassian.com/v1/mcp`) antes de usar `mcp__atlassian__*`. Deletar comentário Jira não tem tool MCP — usar REST `DELETE /rest/api/3/issue/{key}/comment/{id}` com basic auth do `.env`.

## In Progress

Nada em andamento. v2 entregue, validado, documentado.

Próximo: v3 (ver Backlog).

## Open Questions / Hypotheses

Nenhuma.

## Known Broken

Nada.

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
- **Jira Coding Agent v3** — `pr-agent.yaml` (auto-fix de CI no PR do agente via action oficial em `workflow_run`/`issue_comment`, com loop-guard), dry-run via `workflow_dispatch`, extração da lógica para CLI Python testado. Gate de ambiguidade dropado: a premissa é que só issues refinadas (negócio + técnico) são delegadas ao agente, então o risco de ambiguidade chegar é absorvido pelo processo upstream.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

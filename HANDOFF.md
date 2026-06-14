# Handoff

## Why

Jira Coding Agent v2 entregue: agente lê issue do Jira, implementa, abre PR, comenta no Jira e transiciona pra "In Review". Implementação via `claude-code-action` + App "Claude". Alternativa rejeitada: `claude -p` headless cru (mais cola para auth/PR; a action cunha token internamente a partir do `CLAUDE_CODE_OAUTH_TOKEN`).

**Setup live (não recriar):**
- Site `smsilva.atlassian.net`, projeto `PLTF`. Issue de teste: **PLTF-11**.
- Automation rule "Jira Coding Agent — manual trigger": `POST https://api.github.com/repos/smsilva/wasp-agent/dispatches`, body `event_type=jira-trigger-event` + `client_payload.issue_key={{issue.key}}`. Disparar via issue → menu `• • •` → Automation.
- PAT fine-grained "jira" (escopo `smsilva/wasp-agent`, `Contents: write` + `Actions: write`) no header `Authorization: Bearer <PAT>` da rule (fica no Jira).
- Secrets no repo: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`. Valores Jira também no `.env` local.
- Settings → Actions → General: flag "Allow GitHub Actions to create and approve pull requests" ligada (sem ela, `gh pr create` falha com GraphQL `createPullRequest`).
- Primeiro PR de cada novo branch do bot exige aprovação manual ("Approve workflows to run").

Atlassian MCP não está no catálogo `mcp --list`; conectar via `/mcp` (`claude mcp add http https://mcp.atlassian.com/v1/mcp`) antes de usar `mcp__atlassian__*`. Deletar comentário Jira não tem tool MCP — usar REST `DELETE /rest/api/3/issue/{key}/comment/{id}` com basic auth do `.env`.

**v3/SEC-008 entregue 2026-06-13**: artefato de execução do agente gateado em `if: failure()` + `retention-days: 7`. Spec `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v3-sec-008.md`; plano `docs/sdlc/03-execution/2026-06-13-jira-coding-agent-v3-sec-008.md`. Validação manual pós-merge ainda pendente: disparar PLTF-11 (run verde → sem artefato; falha forçada → artefato com 7d).

**v3/ci-fix-agent entregue e validado end-to-end 2026-06-14**: dois workflows fecham o ciclo de CI no PR do `jira-agent`. `ci-fix-notifier.yaml` detecta falha em branch `claude/*` e posta convite `/fix`. `ci-fix-agent.yaml` recebe `/fix [--max-attempts N]` (default 3), conta tentativas via marcador `<!-- ci-fix-attempt -->`, aciona `claude-code-action`, ou esgota e transiciona Jira para "In Progress". Spec `docs/sdlc/02-design/2026-06-14-ci-fix-agent.md`; plano `docs/sdlc/03-execution/2026-06-14-ci-fix-agent.md`. Validação capturou bug (`gh pr list --head` aceita branch name, não SHA) já corrigido — documentado em `CLAUDE.md::GitHub Actions`.

## In Progress

Nada em andamento. Próximo: escolher entre os 2 specs restantes da v3 e abrir brainstorming.

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

- Validação manual pós-merge do v3/SEC-008 (pendente desde 2026-06-13): disparar `gh workflow run jira-agent.yaml -f jira_issue=PLTF-11`; run verde → sem artefato. Forçar falha → artefato com 7d.
- Próximo spec da v3 (2 restantes): dry-run via `workflow_dispatch`, OU extração de `scripts/jira-*` + `scripts/ensure-pr` para CLI Python testado.

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
- **Jira Coding Agent v3** (2 specs restantes) — ci-fix-agent e SEC-008 entregues. Itens pendentes: dry-run via `workflow_dispatch`, extração da lógica para CLI Python testado. Gate de ambiguidade dropado: só issues refinadas (negócio + técnico) são delegadas ao agente, então o risco é absorvido pelo processo upstream.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

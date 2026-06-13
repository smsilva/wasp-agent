# Handoff

## Why

Jira Coding Agent — walking skeleton v1. Hipótese a validar: Jira → atribui issue ao agente → dispara GitHub Actions → comenta de volta no Jira. Prova o round-trip e a autenticação nos dois sentidos antes de qualquer implementação de código real.

Entregue v1 (skeleton):
- `.github/workflows/jira-agent.yaml` — trigger `repository_dispatch` (`types: [jira-trigger-event]`). Skeleton com um step por etapa do pipeline alvo; só leitura da issue key e comentário no Jira são reais, o resto loga "would …". Issue key vinda de `client_payload` é validada por regex (`^[A-Z]+-[0-9]+$`) via env var antes de uso — evita injeção de comando.
- `scripts/jira-comment` — bash+curl+jq, posta comentário ADF em `/rest/api/3/issue/{key}/comment` (basic auth). Testado em `tests/test_jira_comment.py` via mock HTTP server.
- `docs/runbooks/jira-coding-agent-setup.md` — passo a passo reproduzível (Jira Automation, secrets, validação, troubleshooting).

Design: `docs/sdlc/02-design/2026-06-13-jira-coding-agent.md`. Plano: `docs/sdlc/03-execution/2026-06-13-jira-coding-agent.md`.

Hipótese **validada ponta a ponta com o Jira no loop** (2026-06-13): a Automation rule do projeto PLTF (trigger "Manual trigger from work item") dispara `repository_dispatch` → workflow roda no `main` → comenta de volta na issue. Confirmado pela PLTF-11 (run `27472803427`, success, comentário "Agent picked this up…"). Também validados `workflow_dispatch` e `repository_dispatch` via `gh api`. Secrets `JIRA_*` configurados no repo; `checkout@v5` no `main` (sem warning Node 20). Config Jira local em `.jira/config.md` (gitignored).

Gotchas do setup da Automation rule (no runbook): header `Authorization` exige prefixo `Bearer ` (401 sem); PAT precisa de `Contents: write`, não basta `Actions: write` (403); não usar o botão "Validate" do Send web request (roda sem contexto → `{{issue.key}}` vazio).

## In Progress

Nenhum trabalho em andamento. v1 entregue e validado end-to-end (código + infra + Jira).

Próximo passo natural é a v2 (ver Backlog): implementação real com `claude -p`, branch, PR, transição "In Review".

## Open Questions / Hypotheses

Nenhuma.

## Known Broken

Nenhum.

## How to Resume

```bash
make test 2>&1 | tail -5
```

Confirmar `423 passed, 1 skipped`, 100% coverage.

## Next Steps

Nenhum item priorizado. Ver Backlog.

## Backlog (carry-over)

- **Parser duplicado de `session_id`.** `wasp/watches/__init__.py:restore_pending_watches` repete a lógica de `extract_channel`/`extract_chat_id` em `wasp/watcher.py`. Extrair `parse_session_id(raw) -> tuple[str, str] | None` em `wasp/watcher.py` quando aparecer terceiro caller (regra das três usos do CLAUDE.md).
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
- **Jira Coding Agent v2/v3** (`docs/sdlc/03-execution/2026-06-13-jira-coding-agent.md`) — v2: implementação real com `claude -p`, GitHub App, branch, PR, transição "In Review". v3: gate de ambiguidade, `pr-agent.yaml` (auto-fix de CI via action oficial), `workflow_dispatch`/dry-run, extração para CLI Python testado.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

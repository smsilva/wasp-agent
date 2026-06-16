# Handoff

## Why

Sessão dedicada a polish do deck `docs/presentations/2026-06-15-jira-coding-agent.pptx`: traduzir para inglês, trocar tons de azul por preto/branco/cinza, aplicar fundo de chalkboard, escurecer fundo 30%, slide 2 com título cinza/subtítulo branco, remover linha decorativa inferior (skill `pptx` atualizada para não voltar a sugerir), caixas do slide 8+ no estilo do slide 9 (ativa = preta `#1A1A1A` sem borda; inativa = cinza `#808080` 25% alpha sem borda, texto camuflado).

Texto inativo dos slides 3-7 (bullets em "Motivation") + título "From ticket to PR" dos slides 9-12 atualizados para **Dark Gray 1 = `#666666`**, confirmado deterministicamente via re-extração do `.pptx` salvo.

Aprendizado central capturado em `~/git/linux/claude/rules/pptx.md`: mapping correto LibreOffice → hex é `Dark Gray 1 = #666666` (eu havia gravado errado como `#1C1C1C`; a auditoria determinística mentiu por confirmação circular até o usuário inverter o swatch ao vivo no LibreOffice).

## In Progress

Nada em andamento. Última ação: usuário abriu o deck no LibreOffice para inspeção visual (sem mais edits relatados).

## Open Questions / Hypotheses

Nenhuma.

## Known Broken

Nada.

## How to Resume

```bash
xdg-open /home/silvios/git/wasp-agent/docs/presentations/2026-06-15-jira-coding-agent.pptx
```

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

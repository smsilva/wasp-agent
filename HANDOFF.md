# Handoff

## Why

Pedido "checklist de production readiness" foi respondido ad-hoc apesar de existir `docs/references/project-scaffolding-checklist.md` cobrindo o mesmo terreno — agente esqueceu da doc. Causa: nome sugeria só scaffolding e não havia entrada em `CLAUDE.md` apontando para ele.

Solução desta sessão:

- Renomeado `docs/references/project-scaffolding-checklist.md` → `docs/references/production-readiness-checklist.md` (git mv preserva histórico).
- Reescrita a intro do checklist cobrindo dois usos: scaffolding inicial + PRR pré-deploy.
- Importado vocabulário **gate/score** e níveis **Bronze/Prata/Ouro** do `good-citizen-test.md`.
- Nova seção 12 "Canais de entrada (multi-channel)" — gap detectado no rascunho ad-hoc.
- Seção "Uso por agente" agora descreve fluxos separados de scaffolding e PRR.
- `CLAUDE.md`: nova seção `## Production readiness` com regra de discoverability + entrada em `## External references`.
- `~/Downloads/good-citizen-test.md` copiado para `docs/sdlc/02-design/2026-05-30-good-citizen-test.md` (é spec de feature `waspctl good-citizen`, não referência viva).

Alternativa rejeitada: manter o nome `project-scaffolding-checklist.md`. Descartado porque o documento é usado também em PRR pré-deploy, não só greenfield.

## In Progress

Sessão pediu commit ao final via `/commit`. Mudanças staged/unstaged:

- `renamed: docs/references/project-scaffolding-checklist.md -> docs/references/production-readiness-checklist.md` (staged pelo `git mv`)
- `modified: CLAUDE.md` (unstaged)
- `modified: docs/references/production-readiness-checklist.md` (unstaged)
- `untracked: docs/sdlc/02-design/2026-05-30-good-citizen-test.md`

Próximo passo: dois commits separados conforme proposto ao usuário:

1. `docs(refs): rename to production-readiness-checklist and add PRR usage` — inclui o rename, edição no checklist e a entrada nova em `CLAUDE.md`.
2. `docs(sdlc): add good-citizen-test design spec` — só o arquivo novo em `sdlc/02-design/`.

## Open Questions / Hypotheses

- O slug `2026-05-30-good-citizen-test.md` segue a convenção do `CLAUDE.md` ("mesmo slug para o par design+execução"). Quando o plano de execução for escrito, usar o mesmo slug em `docs/sdlc/03-execution/`.
- Implementar `waspctl good-citizen run` requer decisão sobre onde mora `waspctl` — hoje não existe CLI separado do `wasp-agent`. Pode entrar como subcomando do CLI atual (`auth_cli.py` é o único hoje) ou como projeto irmão.

## Known Broken

Nada. Mudanças são puramente documentais — nenhum código tocado, validações originais do branch `dev` continuam válidas (290 testes unit + 1 e2e, 100% cov, ruff clean).

## How to Resume

```bash
cd /home/silvios/git/wasp-agent && git status
```

Esperado: rename staged + 2 modificados + 1 untracked listados em "In Progress".

## Next Steps

1. Revisar diff final dos dois arquivos editados:
   - `git diff CLAUDE.md`
   - `git diff docs/references/production-readiness-checklist.md`
2. Stage seletivo e commit 1: `git add CLAUDE.md docs/references/production-readiness-checklist.md` (rename já staged) + mensagem `docs(refs): rename to production-readiness-checklist and add PRR usage`.
3. Stage e commit 2: `git add docs/sdlc/02-design/2026-05-30-good-citizen-test.md` + mensagem `docs(sdlc): add good-citizen-test design spec`.
4. Depois retomar os Next Steps do handoff anterior: merge `dev` → `main` e escolher próxima feature (discord slash commands / LLM behavior eval / OTel tracing).

## Carry-over do handoff anterior

Backlog, Idea-stage explorations e Next Steps do handoff anterior continuam válidos — não duplicar aqui. Recuperar com `git show HEAD:HANDOFF.md` antes do commit desta sessão.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
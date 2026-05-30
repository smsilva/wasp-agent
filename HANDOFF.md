# Handoff

## Why

(sem trabalho ativo)

## In Progress

Nada.

## Open Questions / Hypotheses

Nenhuma.

## Known Broken

Nada conhecido.

## How to Resume

`git status`, `git log -5` para contexto recente.

## Next Steps

Selecionar item do Backlog conforme prioridade.

## Backlog (carry-over)

- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`)
- **Handler de convite via DM no Discord** — ver `wasp/clients/telegram/webhook.py` como referência
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`)
- **Próximo CRD: `Cluster`** — padrão `wasp/resources/cluster/{manifest,provisioner,inventory}.py`
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** (ex: `wasp/session.py`) quando terceiro CRD chegar
- **Status check manual** — tool para consultar Platform sem watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — admin, operator, viewer
- **Testcontainers** — avaliar substituir setup manual k3d/Gitea no E2E
- **Falha clara em configuração ausente** — validar env obrigatórias no startup
- **PostgresAuthRepository** — implementar quando migração for priorizada (Protocol já pronto, singleton já exercitado pelos callers)
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

# Handoff

## Why

Refactor de `wasp/auth.py` (310 linhas, 4 responsabilidades) em pacote `wasp/auth/` com Repository Protocol + implementação SQLite. Motivação: migração futura para Postgres em cloud gerenciada justifica a abstração. Implementação **concluída** e validada (`make e2e-with-debug` passou).

Próximo ciclo: **migração de callers para `auth.get_repository()` e remoção dos shims funcionais**. Spec em `docs/sdlc/02-design/2026-05-30-auth-singleton-migration.md`. Objetivo é fazer o singleton ser efetivamente exercitado pelos callers (hoje ele é código pouco usado — shims sempre criam instância descartável) para que Postgres com pool de conexões funcione naturalmente.

Alternativas rejeitadas:
- Injeção explícita do repo nos construtores (mais Pythonic, custo de refatoração maior — adiado).
- Manter shims após migração (mantém duplicação de entrypoints).

Decisões fechadas na conversa:
1. Deletar `tests/test_auth.py` (duplica `tests/test_auth_repository.py`).
2. Em `webhook.py`, usar `lambda *a: auth.get_repository().redeem_invite(*a)` (lazy) em vez de bound method (que ficaria bound a instância antiga após `_reset_repository`).
3. Remover o alias `init_db` — `main.py` chamará `auth.get_repository().init_schema()` direto.

## In Progress

Plano de execução gerado em `docs/sdlc/03-execution/2026-05-30-auth-singleton-migration.md` (10 tasks, TDD-style com commits incrementais). Próximo passo: executar via `superpowers:subagent-driven-development` ou `superpowers:executing-plans`.

## Open Questions / Hypotheses

- Nenhuma aberta na spec. Antes de implementar, confirmar paridade caso a caso entre `test_auth.py` e `test_auth_repository.py` — se algum cenário só existe em `test_auth.py`, migrar para `test_auth_repository.py` antes de deletar.

## Known Broken

Nada. *Intentional*: shim `_repo(None)` ainda cria instância descartável por chamada (mantido após sessão anterior por incompatibilidade com `sys.modules.pop` no `mock_agno`). Essa decisão é justamente o que a próxima migração elimina.

## How to Resume

```bash
xdg-open docs/sdlc/03-execution/2026-05-30-auth-singleton-migration.md
```

Executar o plano task a task — recomendado via `superpowers:subagent-driven-development` (fresh subagent por task + review entre tasks) ou `superpowers:executing-plans` (batch inline com checkpoints).

## Next Steps

1. Executar Tasks 1–10 do plano em ordem.
2. Atualizar Status do spec para `Implemented` (Task 10).
3. Limpar este HANDOFF.md (Task 10).

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
- **PostgresAuthRepository** — implementar quando migração for priorizada (Protocol já pronto)
- **`waspctl good-citizen`** (`docs/sdlc/02-design/2026-05-30-good-citizen-test.md`) precisa de plano de execução

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

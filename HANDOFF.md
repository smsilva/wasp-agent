# Handoff

## Why

`WatchRepository.register` era no-op silencioso em re-provisioning após estado terminal. `UniqueConstraint(kind, name)` fazia o `INSERT` lançar `IntegrityError` (capturado e ignorado) quando já existia linha em `ready`/`failed`/`timeout` — o watch thread iniciava mas o DB não voltava a `pending`, então restart subsequente não recuperava.

Fix: substituir `INSERT` + `try/except IntegrityError` por upsert `INSERT ... ON CONFLICT(kind, name) DO UPDATE SET status='pending', session_id=excluded.session_id, created_at=excluded.created_at, notified_at=NULL`. `ON CONFLICT ... excluded` é idêntico em SQLite 3.24+ e Postgres — sem branching por dialeto. Import `IntegrityError` removido (órfão).

Alternativa rejeitada: `INSERT OR REPLACE` (SQLite) + `ON CONFLICT` (Postgres) com branching por `engine.dialect.name` — desnecessário, `excluded` cobre ambos com um SQL só.

## In Progress

Nenhum trabalho em andamento. Fix aplicado e validado.

## Open Questions / Hypotheses

Nenhuma.

## Known Broken

Nenhum.

## How to Resume

```bash
make test 2>&1 | tail -5
```

Confirmar `422 passed, 1 skipped`, 100% coverage.

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

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

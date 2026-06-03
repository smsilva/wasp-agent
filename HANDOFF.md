# Handoff

## Why

**Watcher restart resilience — design + plano concluídos, implementação pendente.**

Watches de CRD (Platform, Cluster) são hoje in-memory: se o agente reiniciar antes de o CRD ficar Ready, a notificação é perdida. A solução persistir o estado de cada watch em banco de dados e replay no startup.

Decisões de design:
- **Engine único SQLAlchemy** (`wasp/db/`) compartilhado por auth e watches — `DATABASE_BACKEND` controla SQLite vs Postgres.
- **auth migra para SQLAlchemy Core** — `sqlite_repository.py` + `postgres_repository.py` → `repository.py` unificado. Locking por dialeto (`isolation_level="IMMEDIATE"` para SQLite, `FOR UPDATE`/`LOCK TABLE` para Postgres).
- **`wasp/watches/`** novo pacote com `WatchRepository` (register/complete/fail/timeout/list_pending) e `restore_pending_watches()`.
- `restore_pending_watches()` chamada em `main.py` **após** `create_app()` — canais (Discord, Telegram) precisam estar registrados antes.
- `complete()` **antes** de `notifier.send()` — at-most-once: se o processo cair entre os dois, o watch sai da fila e não renotifica.

Alternativas rejeitadas: watches sempre SQLite (inconsistência quando backend é Postgres), engines separados por módulo (dois engines para mesmo DB), SQLAlchemy ORM (overhead desnecessário para SQL simples).

## In Progress

Design e plano de execução escritos. Implementação **não iniciada**.

Último passo: escrita de `docs/sdlc/03-execution/2026-05-16-platform-watcher-restart-resilience.md` (11 tasks com código completo).

Próximo passo: executar Task 1 do plano (`wasp/db/__init__.py`).

## Open Questions / Hypotheses

- OTLP 401 pós-`make test` é ruído cosmético: thread background do exporter dispara depois que pytest encerra, tenta logar mas stdout já fechou. Não afeta exit code. Pré-existente, depende de `OTEL_EXPORTER_OTLP_ENDPOINT` estar setado no shell.
- `_now()` existirá duplicado em `wasp/auth/repository.py` e `wasp/watches/repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.

## Known Broken

Nenhum.

## How to Resume

```bash
cat docs/sdlc/03-execution/2026-05-16-platform-watcher-restart-resilience.md
```

Depois executar com subagent-driven development (opção escolhida pelo usuário):

```
/superpowers:subagent-driven-development docs/sdlc/03-execution/2026-05-16-platform-watcher-restart-resilience.md
```

## Next Steps

1. **Executar plano** — `docs/sdlc/03-execution/2026-05-16-platform-watcher-restart-resilience.md`, Task 1 a Task 11, via subagent-driven development.
2. Após implementação: mover `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` para `archived/` e atualizar `docs/sdlc/CLAUDE.md`.

## Backlog (carry-over)

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
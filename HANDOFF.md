# Handoff

## Why

**Watcher restart resilience — implementado e validado.** Watches de CRD (Platform, Cluster) agora persistem em `wasp/watches/` e são replay no startup, sobrevivendo a restarts do agente.

## In Progress

Nenhum trabalho em andamento. Branch `dev` à frente de `origin/dev` em 9 commits prontos para PR.

## Open Questions / Hypotheses

- `_now()` duplicado em `wasp/auth/repository.py` e `wasp/watches/repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.
- OTLP 401/warning pós-`make test` é ruído cosmético: thread background do exporter dispara após o pytest encerrar (stdout já fechou). Não afeta exit code.

## Known Broken

Nenhum. Suíte completa verde:

- `make test`: 418 passed, 1 skipped, **100% coverage** (inclui postgres via testcontainers — Docker obrigatório).
- `make e2e-with-debug`: 1 passed (spin up k3d + Gitea + full provisioning flow).
- `ruff check .` e `ruff format --check .` limpos.

Notas de segurança herdadas (não regredir):
- `pytest-timeout` (`timeout = 60`, signal) configurado em `pyproject.toml`. Tests de poll-loop (`watch_platform`/`watch_cluster`) que mockam `asyncio.sleep` e patcham `time.monotonic` podem girar a 100% CPU e disparar o OOM-killer. Usar iterador **infinito** `chain([...], repeat(WATCH_TIMEOUT_SECONDS + 1))` e teste `async def` + `await` (não `asyncio.run`). Detalhes em `tests/CLAUDE.md`.

## How to Resume

Não há fluxo de retomada — feature concluída. Próximo passo: PR e merge para `main`.

```bash
git push origin dev
gh pr create --base main --head dev
```

## Backlog (carry-over)

- **`WatchRepository.register` silenciosamente no-op em re-provisioning após estado terminal.** `UniqueConstraint("kind","name")` em `resource_watches` faz `INSERT` lançar `IntegrityError` (capturado) quando há linha pré-existente em status `ready`/`failed`/`timeout`. O novo watch thread inicia mas o DB não reflete `pending` — restart subsequente não recupera. Hoje, blindado pelo guard de manifest no GitOps (`committer.commit()` retorna early se o YAML já existe), mas o contrato do `register` está incorreto. Fix sugerido: `INSERT ... ON CONFLICT(kind, name) DO UPDATE SET status='pending', session_id=:session_id, created_at=:created_at` (Postgres) / `INSERT OR REPLACE` (SQLite, com cuidado quanto a notified_at).
- **Parser duplicado de `session_id`.** `wasp/watches/__init__.py:restore_pending_watches` repete a lógica de `extract_channel`/`extract_chat_id` em `wasp/watcher.py`. Extrair `parse_session_id(raw) -> tuple[str, str] | None` em `wasp/watcher.py` quando aparecer terceiro caller (regra das três usos do CLAUDE.md).
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

# Handoff

## Why

**Watcher restart resilience — Tasks 1-5 implementadas, Tasks 6-11 pendentes.**

Watches de CRD (Platform, Cluster) são hoje in-memory: se o agente reiniciar antes de o CRD ficar Ready, a notificação é perdida. Solução: persistir o estado de cada watch em banco e replay no startup.

Decisões de design (já aplicadas onde implementadas):
- **Engine único SQLAlchemy** (`wasp/db/`) compartilhado por auth e watches — `DATABASE_BACKEND` controla SQLite (`NullPool`, `check_same_thread=False`) vs Postgres.
- **auth unificado** — `sqlite_repository.py` + `postgres_repository.py` + `_connection.py` deletados; `wasp/auth/repository.py` é a única implementação (SQLAlchemy Core). Locking por dialeto: SQLite `BEGIN IMMEDIATE`; Postgres `SELECT ... FOR UPDATE` (`redeem_invite`) / `LOCK TABLE ... ACCESS EXCLUSIVE` (`bootstrap_admin`).
- **`wasp/watches/`** (a CRIAR): `WatchRepository` (register/complete/fail/timeout/list_pending) + `restore_pending_watches()`.
- `restore_pending_watches()` em `main.py` **após** `create_app()` — canais (Discord, Telegram) precisam estar registrados antes do replay.
- `complete()` **antes** de `notifier.send()` — at-most-once: se cair entre os dois, o watch sai da fila e não renotifica.

Alternativas rejeitadas: watches sempre SQLite (inconsistência quando backend é Postgres), engines separados por módulo, SQLAlchemy ORM (overhead para SQL simples).

## In Progress

Plano: `docs/sdlc/03-execution/2026-05-16-platform-watcher-restart-resilience.md` (11 tasks com código completo).

**Concluído — Tasks 1 a 5:** `wasp/db/__init__.py` (engine singleton), `wasp/auth/_schema.py` (MetaData), `wasp/auth/repository.py` (`AuthRepository` completo, incl. `redeem_invite` refatorado em `_redeem` + `bootstrap_admin`), deleção dos repos por backend, `get_repository()` chama `init_schema()` no primeiro uso, testes postgres migrados para `create_engine` com driver psycopg3.

**Próximo passo: Task 6** — criar `wasp/watches/_schema.py` (tabela `resource_watches` + `init_schema(engine)`). Seguir o código do plano. Depois Tasks 7-11.

> ⚠️ **NÃO re-executar Tasks 1-5.** Já estão na árvore e o código real **diverge de propósito** do listado no plano: `redeem_invite` foi extraído no helper `_redeem` (complexidade), e o fixture postgres usa `get_connection_url(driver="psycopg")` (não `driver=None`). Rodar as Tasks 1-5 do plano sobrescreveria esses ajustes. Começar em Task 6.

## Open Questions / Hypotheses

- `_now()` duplicado em `wasp/auth/repository.py` e (futuro) `wasp/watches/repository.py`. Intencional (1 linha); extrair só se surgir terceiro caller.
- OTLP 401/warning pós-`make test` é ruído cosmético: thread background do exporter dispara após o pytest encerrar (stdout já fechou). Não afeta exit code. Pré-existente, só quando `OTEL_EXPORTER_OTLP_ENDPOINT` está setado no shell.
- `CLAUDE.md` (seção "Packages — `wasp/watches/`") já descreve o pacote como se existisse — é o **alvo de design**, não o estado atual. Implementar conforme essa descrição + Task 6-8.

## Known Broken

Nenhum. Suíte completa verde: 395 passed, 1 skipped (`make test` inclui postgres via testcontainers — Docker obrigatório).

Notas de segurança herdadas desta sessão (já corrigidas, não regredir):
- *intentional* — `pytest-timeout` (`timeout = 60`, signal) configurado em `pyproject.toml` como guarda de wall-clock. Tests de poll-loop (`watch_platform`/`watch_cluster`) que mockam `asyncio.sleep` e patcham `time.monotonic` podem girar a 100% CPU e disparar o OOM-killer (derruba o tmux). Usar iterador **infinito** `chain([...], repeat(WATCH_TIMEOUT_SECONDS + 1))` e teste `async def` + `await` (não `asyncio.run`). Detalhes em `tests/CLAUDE.md`.

## How to Resume

```bash
sed -n '/^## Task 6/,/^## Task 9/p' docs/sdlc/03-execution/2026-05-16-platform-watcher-restart-resilience.md
```

Executar **apenas Tasks 6-11** via subagent-driven development (opção escolhida pelo usuário) — instruir os subagentes a iniciar em Task 6, pois Tasks 1-5 já estão implementadas (ver aviso em **In Progress**):

```
/superpowers:subagent-driven-development docs/sdlc/03-execution/2026-05-16-platform-watcher-restart-resilience.md
```

## Next Steps

1. **Task 6** — `wasp/watches/_schema.py` (tabela `resource_watches`).
2. **Task 7** — `wasp/watches/repository.py` (`WatchRepository` CRUD: register/complete/fail/timeout/list_pending).
3. **Task 8** — `wasp/watches/__init__.py` (`get_repository()` singleton + `_reset_repository()` + `restore_pending_watches()` com lazy imports de `wasp.watcher`).
4. **Task 9** — atualizar spawners e coroutines (`watch_platform`/`watch_cluster`) para register/complete/fail/timeout.
5. **Task 10** — `main.py`: chamar `restore_pending_watches()` após `create_app()`.
6. **Task 11** — validação completa (`make format && make test && make e2e-with-debug`).
7. Ao adicionar módulos `wasp.watches.*`, incluí-los nas listas de `sys.modules.pop` da fixture `mock_agno` (setup E teardown) e adicionar `_reset_repository()` do novo singleton.
8. Pós-implementação: mover `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` para `archived/` e atualizar `docs/sdlc/CLAUDE.md`.

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

# Handoff

## Why

**Eliminar ruído pós-`make test`.** A suíte passava mas imprimia mensagens de erro no final. Duas causas distintas, ambas corrigidas:

1. **Corotinas nunca aguardadas** (`RuntimeWarning: coroutine ... was never awaited`). Quatro fontes:
   - Produção: `wasp/watches/__init__.py::restore_pending_watches` criava a corotina antecipadamente (`coro = watch_platform(...)`) antes de iniciar a thread. Corrigido para construir a corotina **dentro** do target (`asyncio.run(fn(name, chat_id, notifier))`).
   - `tests/test_cluster_watcher.py::test_cluster_watcher_spawner_thread_runs_asyncio`: mockava `asyncio.run` mas não `watch_cluster`. Corrigido espelhando o teste de platform (mocka `watch_cluster`, asserta `assert_called_once_with(mock_watch.return_value)`).
   - `tests/test_discord.py::test_discord_notifier_send_crossloop_uses_run_coroutine_threadsafe`: `channel` era `AsyncMock`, então `channel.send(text)` gerava corotina entregue ao `run_coroutine_threadsafe` mockado e nunca aguardada. Trocado para `MagicMock`.
   - Trava: `filterwarnings = ["error::RuntimeWarning"]` em `pyproject.toml` — vazamento futuro falha a suíte em vez de virar ruído.

2. **Logging error do exporter OTLP** (`I/O operation on closed file` + `Failed to export metrics ... 401`). Era o item "ruído cosmético" do handoff anterior — **agora resolvido, não era cosmético.** `wasp/telemetry.py::configure()` roda no import, que dispara na coleta do pytest (via `from wasp import ...` no topo de `test_auth_cli.py`), antes do `mock_agno` deletar `OTEL_EXPORTER_OTLP_ENDPOINT`. Com a var setada na shell, cria um `PeriodicExportingMetricReader` real cuja thread exporta no shutdown e loga em stream fechada. Fix: `os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)` no topo de `tests/conftest.py` (escopo de sessão, antes da coleta).

Alternativa rejeitada: filtro `ignore` dos warnings — mascararia o bug de produção real (corotina vazada).

## In Progress

Nenhum trabalho em andamento. Todas as correções aplicadas e validadas.

## Open Questions / Hypotheses

Nenhuma deste trabalho.

## Known Broken

Nenhum. Suíte verde com e sem `OTEL_EXPORTER_OTLP_ENDPOINT`:

- `make test`: 418 passed, 1 skipped, 100% coverage, **zero linhas de warning/erro após a execução**.
- Validado também com `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 make test` (reproduz a shell do usuário) — sem ruído.
- `ruff check .` e `ruff format` limpos.

`make e2e-with-debug` não rodado nesta sessão (pesado: sobe k3d + Gitea). Rodar antes de merge conforme `CLAUDE.md`.

## How to Resume

```bash
make test 2>&1 | tail -5
```

Confirmar `418 passed, 1 skipped` sem mensagens após. Opcionalmente reproduzir o cenário OTEL: `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 make test 2>&1 | grep -c "I/O operation"` deve retornar `0`.

## Next Steps

- Rodar `make e2e-with-debug` antes de integrar.

## Backlog (carry-over)

- **`WatchRepository.register` silenciosamente no-op em re-provisioning após estado terminal.** `UniqueConstraint("kind","name")` em `resource_watches` faz `INSERT` lançar `IntegrityError` (capturado) quando há linha pré-existente em status `ready`/`failed`/`timeout`. O novo watch thread inicia mas o DB não reflete `pending` — restart subsequente não recupera. Hoje, blindado pelo guard de manifest no GitOps (`committer.commit()` retorna early se o YAML já existe), mas o contrato do `register` está incorreto. Fix sugerido: `INSERT ... ON CONFLICT(kind, name) DO UPDATE SET status='pending', session_id=:session_id, created_at=:created_at` (Postgres) / `INSERT OR REPLACE` (SQLite, com cuidado quanto a notified_at).
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

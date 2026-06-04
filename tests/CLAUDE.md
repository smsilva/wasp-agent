# tests/

## Postgres tests via testcontainers

Tests marked `postgres` (`test_postgres_auth_repository.py`, `test_postgres_skeleton.py`) spin a real `postgres:16-alpine` via testcontainers and run inside `make test` — Docker required, not gated. The container is a session-scoped fixture (`pg_url`); per-test isolation via `TRUNCATE ... CASCADE`, not a fresh DB. They run under autouse `mock_agno` (no bypass) since importing `wasp.auth` needs agno mocked.

URL driver depends on the client: raw `psycopg.connect()` accepts `pg.get_connection_url(driver=None)` (`postgresql://...`), but SQLAlchemy `create_engine` needs the explicit driver — use `pg.get_connection_url(driver="psycopg")` (`postgresql+psycopg://...`). `driver=None` with `create_engine` defaults to the psycopg2 dialect, which isn't installed (`psycopg[binary]` is v3) → `ModuleNotFoundError: psycopg2`.

## `mock_agno` fixture and OTEL

`tests/conftest.py` mocks `agno.models` as `MagicMock`. If `OTEL_EXPORTER_OTLP_ENDPOINT` is set in the shell, `configure()` calls `AgnoInstrumentor` which imports `agno.models.base.Model` and fails against the mock — the fixture delenvs it; don't remove that line.

`configure()` também roda no **import** de `wasp.telemetry`, que dispara na *coleta* do pytest (via `from wasp import ...` no topo de `test_auth_cli.py`) — antes de qualquer fixture. Se a shell exporta `OTEL_EXPORTER_OTLP_ENDPOINT`, cria um `PeriodicExportingMetricReader` real cuja thread exporta no shutdown e loga em stream fechada (`I/O operation on closed file`). O topo do `conftest.py` faz `os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)` em escopo de sessão para cobrir isso; o `delenv` por-teste do `mock_agno` sozinho não basta. Não remover nenhum dos dois.

The `sys.modules.pop` loop must include every `wasp.*` module. When adding a new module in `wasp/`, add it to the fixture list or state leaks between tests causing intermittent failures. Para pacotes (ex: `wasp/auth/`), incluir o pacote E todos os submódulos (`wasp.auth`, `wasp.auth.protocol`, `wasp.auth.repository`, etc.).

Pacotes com singleton (`get_repository()` em `wasp/auth/__init__.py`, `wasp/watches/__init__.py`) precisam de reset explícito no setup/teardown da fixture `mock_agno` — `sys.modules.pop` não invalida bindings já importados. Capturar a referência do módulo **antes** do `sys.modules.pop`; fazer o `get` depois retorna `None` e o reset é silenciosamente pulado.

`wasp.db` tem singleton `get_engine()` / `_reset_engine()` — chamar `_reset_engine()` junto com `_reset_repository()` do auth no setup e teardown do `mock_agno`, caso contrário testes que mudam `DATABASE_FILE`/`DATABASE_BACKEND` via `monkeypatch.setenv` vazam o engine entre testes.

Testes que precisam mockar auth devem fazer `monkeypatch.setattr(auth.get_repository(), "is_authorized", ...)` — patchando a instância singleton em vez do nome no módulo. O `mock_agno` chama `_reset_repository()` no setup e teardown, garantindo que cada teste começa com singleton limpo e que o patch atinge a instância usada pelo caller.

When testing `telemetry.metrics_endpoint`, patch `wasp.telemetry.generate_latest` — not `prometheus_client.generate_latest`. The name is bound at import time.

## Never-awaited coroutines fail the suite (`filterwarnings`)

`pyproject.toml` sets `filterwarnings = ["error::RuntimeWarning"]` — uma corotina criada e não aguardada (ex: `AsyncMock` chamado mas não awaited, ou corotina criada antes do seu runner) **falha** a suíte em vez de virar ruído no final. O GC reporta o warning em momento arbitrário, então a atribuição ao teste é não-confiável: bisseccione por arquivo (`for f in tests/test_*.py; do ...`) e depois inspecione, não confie no nome do teste no summary. Padrão recorrente: passar `algum_async_mock()` como argumento a um mock que substitui o awaiter real (`asyncio.run`, `run_coroutine_threadsafe`) — a corotina nunca é aguardada. Mocke também a função async, ou use `MagicMock` para o que produz a corotina.

## Poll-loop tests: avoid runaway loops that OOM-kill the session

`watch_platform`/`watch_cluster` poll with `while time.monotonic() < deadline` and `await asyncio.sleep(...)`. A test that mocks `asyncio.sleep` (instant) and patches `time.monotonic` to force the timeout exit can spin at 100% CPU **forever** if the deadline never trips — allocating telemetry/log objects each iteration until the OOM-killer kills the whole session (it can take down tmux). There is no `pytest-timeout` rescue for the suite without the guard below.

Two rules to keep these tests safe:

1. Use an **infinite** monotonic iterator: `times = chain([0, 0], repeat(w.WATCH_TIMEOUT_SECONDS + 1))`. A finite `iter([...])` (or one with a `StopIteration` fallback) gets exhausted by the event loop's own `time.monotonic()` calls, which corrupts the deadline (`deadline = 601 + 600`) so `601 < 1201` loops forever. See `test_watcher.py::test_watch_platform_timeout` for the reference pattern.
2. Prefer `async def` test + `await w.watch_*(...)` over a sync test calling `asyncio.run(...)`. `asyncio.run` creates a fresh loop whose setup reads `time.monotonic()` and pre-consumes the iterator before the production code runs.

`pytest-timeout` (`timeout = 60`, signal method) is configured in `pyproject.toml` as the wall-clock backstop: a runaway loop now fails one test instead of hanging the suite. Keep it.

## Mocked exception classes can't be raised or caught

`mock_agno` mocks `kubernetes.config` as `MagicMock`. `kubernetes.config.ConfigException` is a MagicMock instance, not a `BaseException` subclass — `raise` and `except` both fail with `TypeError`. To test code that catches it, install a real subclass first: `class FakeConfigException(Exception): pass; monkeypatch.setattr(module.config, "ConfigException", FakeConfigException)`. See `tests/test_k8s_reader.py::test_load_kube_config_auto_fallback_local`.

`kubernetes.client.exceptions` is NOT in `KUBE_MODULES` and cannot be imported during tests (`ModuleNotFoundError`). For production code that needs to detect a 404 from `kubernetes.client`, use `getattr(e, "status", None) == 404` with a bare `except Exception` — avoids the import. In tests, raise a `class FakeApiException(Exception): def __init__(self, status): self.status = status` instead of `ApiException`.

## E2E fixture — patch `_select_notifier`, not `TelegramNotifier`

In `tests/e2e/conftest.py`, patch `_select_notifier` directly:

```python
monkeypatch.setattr(wasp.provision, "_select_notifier", lambda *a, **kw: recording_notifier)
```

Patching only `TelegramNotifier` doesn't work: `AGENT_NOTIFIER=console` in `.env` is loaded at import, so `_select_notifier` returns `ConsoleNotifier` before reaching `TelegramNotifier`.

Also monkeypatch `wasp.auth.get_repository().is_authorized` to return a fake `user_id` — without it the auth guard silently returns `{"status": "unauthorized"}` and the test fails downstream at Gitea's `get_file()` with 404. Patcheie a instância do singleton (`wasp.auth.get_repository()`), não a classe `AuthRepository` diretamente.

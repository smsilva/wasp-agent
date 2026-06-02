# tests/

## Postgres tests via testcontainers

Tests marked `postgres` (`test_postgres_auth_repository.py`, `test_postgres_skeleton.py`) spin a real `postgres:16-alpine` via testcontainers and run inside `make test` — Docker required, not gated. Connect with psycopg3 using `pg.get_connection_url(driver=None)` (yields `postgresql://...`). The container is a session-scoped fixture (`pg_url`); per-test isolation via `TRUNCATE ... CASCADE`, not a fresh DB. They run under autouse `mock_agno` (no bypass) since importing `wasp.auth` needs agno mocked.

## `mock_agno` fixture and OTEL

`tests/conftest.py` mocks `agno.models` as `MagicMock`. If `OTEL_EXPORTER_OTLP_ENDPOINT` is set in the shell, `configure()` calls `AgnoInstrumentor` which imports `agno.models.base.Model` and fails against the mock — the fixture delenvs it; don't remove that line.

The `sys.modules.pop` loop must include every `wasp.*` module. When adding a new module in `wasp/`, add it to the fixture list or state leaks between tests causing intermittent failures. Para pacotes (ex: `wasp/auth/`), incluir o pacote E todos os submódulos (`wasp.auth`, `wasp.auth.protocol`, `wasp.auth.sqlite_repository`, etc.).

Pacotes com singleton (`get_repository()` em `wasp/auth/__init__.py`) precisam de `_reset_repository()` no setup/teardown da fixture `mock_agno` — `sys.modules.pop` não invalida bindings já importados. Capturar a referência do módulo **antes** do `sys.modules.pop` (`_auth_teardown = sys.modules.get("wasp.auth")`); fazer o `get` depois retorna `None` e o reset é silenciosamente pulado.

Testes que precisam mockar auth devem fazer `monkeypatch.setattr(auth.get_repository(), "is_authorized", ...)` — patchando a instância singleton em vez do nome no módulo. O `mock_agno` chama `_reset_repository()` no setup e teardown, garantindo que cada teste começa com singleton limpo e que o patch atinge a instância usada pelo caller.

When testing `telemetry.metrics_endpoint`, patch `wasp.telemetry.generate_latest` — not `prometheus_client.generate_latest`. The name is bound at import time.

## Mocked exception classes can't be raised or caught

`mock_agno` mocks `kubernetes.config` as `MagicMock`. `kubernetes.config.ConfigException` is a MagicMock instance, not a `BaseException` subclass — `raise` and `except` both fail with `TypeError`. To test code that catches it, install a real subclass first: `class FakeConfigException(Exception): pass; monkeypatch.setattr(module.config, "ConfigException", FakeConfigException)`. See `tests/test_k8s_reader.py::test_load_kube_config_auto_fallback_local`.

`kubernetes.client.exceptions` is NOT in `KUBE_MODULES` and cannot be imported during tests (`ModuleNotFoundError`). For production code that needs to detect a 404 from `kubernetes.client`, use `getattr(e, "status", None) == 404` with a bare `except Exception` — avoids the import. In tests, raise a `class FakeApiException(Exception): def __init__(self, status): self.status = status` instead of `ApiException`.

## E2E fixture — patch `_select_notifier`, not `TelegramNotifier`

In `tests/e2e/conftest.py`, patch `_select_notifier` directly:

```python
monkeypatch.setattr(wasp.provision, "_select_notifier", lambda *a, **kw: recording_notifier)
```

Patching only `TelegramNotifier` doesn't work: `AGENT_NOTIFIER=console` in `.env` is loaded at import, so `_select_notifier` returns `ConsoleNotifier` before reaching `TelegramNotifier`.

Also monkeypatch `wasp.auth.get_repository().is_authorized` to return a fake `user_id` — without it the auth guard silently returns `{"status": "unauthorized"}` and the test fails downstream at Gitea's `get_file()` with 404. Patcheie a instância do singleton, não o `SqliteAuthRepository` diretamente.

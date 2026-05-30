# tests/

## `mock_agno` fixture and OTEL

`tests/conftest.py` mocks `agno.models` as `MagicMock`. If `OTEL_EXPORTER_OTLP_ENDPOINT` is set in the shell, `configure()` calls `AgnoInstrumentor` which imports `agno.models.base.Model` and fails against the mock — the fixture delenvs it; don't remove that line.

The `sys.modules.pop` loop must include every `wasp.*` module. When adding a new module in `wasp/`, add it to the fixture list or state leaks between tests causing intermittent failures. Para pacotes (ex: `wasp/auth/`), incluir o pacote E todos os submódulos (`wasp.auth`, `wasp.auth.protocol`, `wasp.auth.sqlite_repository`, etc.).

Pacotes com singleton (`get_repository()` em `wasp/auth/__init__.py`) precisam de `_reset_repository()` no setup/teardown da fixture `mock_agno` — `sys.modules.pop` não invalida bindings já importados. Capturar a referência do módulo **antes** do `sys.modules.pop` (`_auth_teardown = sys.modules.get("wasp.auth")`); fazer o `get` depois retorna `None` e o reset é silenciosamente pulado.

Cuidado ao remover `wasp.auth` do `sys.modules.pop`: testes como `test_auth_guard.py` e `test_provision.py` fazem `monkeypatch.setattr("wasp.auth.is_authorized", ...)`, que pytest resolve via `getattr(wasp, "auth")`. Se `wasp` (raiz) for popped mas `wasp.auth` permanecer, o `getattr` falha porque `wasp/__init__.py` recarrega vazio.

When testing `telemetry.metrics_endpoint`, patch `wasp.telemetry.generate_latest` — not `prometheus_client.generate_latest`. The name is bound at import time.

## Mocked exception classes can't be raised or caught

`mock_agno` mocks `kubernetes.config` as `MagicMock`. `kubernetes.config.ConfigException` is a MagicMock instance, not a `BaseException` subclass — `raise` and `except` both fail with `TypeError`. To test code that catches it, install a real subclass first: `class FakeConfigException(Exception): pass; monkeypatch.setattr(module.config, "ConfigException", FakeConfigException)`. See `tests/test_k8s_reader.py::test_load_kube_config_auto_fallback_local`.

## E2E fixture — patch `_select_notifier`, not `TelegramNotifier`

In `tests/e2e/conftest.py`, patch `_select_notifier` directly:

```python
monkeypatch.setattr(wasp.provision, "_select_notifier", lambda *a, **kw: recording_notifier)
```

Patching only `TelegramNotifier` doesn't work: `WASP_AGENT_NOTIFIER=console` in `.env` is loaded at import, so `_select_notifier` returns `ConsoleNotifier` before reaching `TelegramNotifier`.

Also monkeypatch `wasp.auth.is_authorized` to return a fake `user_id` — without it the auth guard silently returns `{"status": "unauthorized"}` and the test fails downstream at Gitea's `get_file()` with 404. O shim funcional em `wasp/auth/__init__.py` preserva esse monkeypatch — patcheie no shim, não em `SqliteAuthRepository`.

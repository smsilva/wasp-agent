# CLAUDE.md

## Principles

**Think first.** State assumptions explicitly. If multiple interpretations exist, present them. If uncertain, ask before implementing.

**Simplicity.** Minimum code that solves the problem. No abstractions for single-use code, no flexibility that wasn't requested, no error handling for impossible scenarios. If 200 lines could be 50, rewrite it.

**Surgical changes.** Touch only what the task requires. Don't refactor adjacent code, reformat, or delete pre-existing dead code (mention it instead). Only clean up orphans your own changes created. Match existing style.

**Goal-driven.** Transform tasks into verifiable goals with success criteria. State a brief plan for multi-step tasks. Loop until verified.

## Code

- Python + `ruff` for formatting + `uv` for dependencies.
- 100% coverage required. Verify with `pytest --cov`.
- `ruff check .` must pass before every commit.

Lint exceptions:
- `# noqa: E402` on imports after `load_dotenv()` in `main.py` (env vars must precede agno imports).
- `# noqa: F401` on `import main` inside test functions (side-effect import).

## Validation (mandatory before PR/merge)

```bash
make format
make test
make e2e-with-debug
```

The three are complementary:
- `make test` mocks agno via `mock_agno` fixture — won't catch real integration bugs (e.g., agno router prefix `/telegram`, `AgentOS` behavior on `import main`).
- `make e2e-with-debug` imports real `main.py`, runs Gitea + k3d + `fake_reconciler`, exercises full turn-1/turn-2/watcher/notification flow.

Don't skip e2e. The `/telegram/webhook` prefix bug (2026-05-23) only surfaced when running e2e after `make test` passed — unit tests used `MagicMock(path="/webhook")` and never hit the real router.

Four validation paths — see index at `docs/runbooks/validation.md`:
- `make e2e` — automated pipeline. k3d barebones, fake_reconciler, Gitea container, `RecordingNotifier`. No Telegram, no real GitOps.
- **Telegram smoke test (manual)** — `make run` + ngrok + webhook (`docs/runbooks/telegram-local-dev.md`). Validates Telegram channel + LLM behavior. No cluster needed.
- **Prometheus** — `make smoke-prometheus` standalone, or `PROMETHEUS_METRICS_ACTIVE=true make run` + `curl /telemetry/prometheus`.
- **Real GitOps (heavy)** — `make gitops-up` / `make gitops-down`. Cluster `k3s-default`, distinct from `wasp-local` of `make k3d-up`. Only for changes in `wasp/provision.py`, `wasp/watcher.py`, or the Composition. See `docs/runbooks/k3d-argocd-wasp-gitops.md`.

## Project structure

### Documentation (`docs/`)

Single source of current state: `HANDOFF.md` at repo root.

Flow for new features: **exploration/ → design/ → execution/**. Each SDLC subfolder uses `archived/` for completed/superseded items.

| Folder | Answers | Content | Archive when |
|---|---|---|---|
| `sdlc/01-exploration/` | *What and why?* | Problem context, alternatives, technical spikes | Exploration led to a design |
| `sdlc/02-design/` | *How will it look?* | Solution spec: architecture, interfaces, expected behavior | Implementation merged to `main` |
| `sdlc/03-execution/` | *How will we build it?* | Step-by-step plan: tasks, order, dependencies, verification criteria | Implementation merged to `main` |
| `architecture/` | Living docs about current system | `<topic>.md` | Never — update in place |
| `references/` | Living docs about external tools/APIs | `<topic>.md` | Never — update in place |
| `runbooks/` | Manual procedures (setup, troubleshooting) | `<topic>.md` | Never — update in place |
| `security/issues/` | Security findings | `SEC-NNN-<slug>.md` | Resolved |

Spec `Status` values: `Idea`, `Draft`, `Approved`, `Implemented`, `Deferred`.

One-line reminders without context go in `HANDOFF.md` **Backlog**, not `sdlc/02-design/`.

Markdown header blocks: when stacking `**Field:**` lines without blank lines between them, end each with **two trailing spaces** so they render as separate lines.

### Packages — `wasp/clients/`

Channel-specific code lives in `wasp/clients/<channel>/`:

```
wasp/clients/
  __init__.py          ← Notifier Protocol only
  telegram/
    __init__.py        ← public re-exports
    notifier.py
    webhook.py
  local/
    notifier.py
```

Re-exports in `__init__.py` need explicit alias to avoid ruff F401: `from wasp.clients.foo import Bar as Bar`. `RecordingNotifier` (test double) lives in `tests/notifiers.py`, not `wasp/clients/`. New channels (Discord, Slack) follow this layout.

### Makefile

When a target needs more than one command, extract to `scripts/<name>` and call it from the target.

### Startup (`wasp/startup.py`)

Contains `startup()`: `configure_logging()`, `GitOpsCommitter.probe()`, `os.umask(0o077)`. Called from `main.py` after `load_dotenv()`.

`load_dotenv()` stays in `main.py` (not `startup()`) because any `import wasp.*` triggers `wasp/__init__.py` → `wasp.provision` → `wasp.telemetry.configure()` at import time. `.env` vars (`OTEL_EXPORTER_OTLP_ENDPOINT`, `PROMETHEUS_METRICS_ACTIVE`) must be loaded before that.

`GitOpsCommitter.probe()` validates `GH_PAT` on startup when set (zero-config). Catches `GithubException`, re-raises as `RuntimeError` to keep callers github-import-free.

## Conventions

### Env vars

Agent configuration uses prefix `WASP_AGENT_` (e.g., `WASP_AGENT_NOTIFIER`).

### Telegram bot tone

System prompt must include explicit anti-pattern instructions:
- No filler ("Sure!", "Perfect!", "Excellent!")
- No emojis, no exclamation marks
- Short paragraphs separated by blank lines
- Avoid bullet lists and bold except when structure genuinely helps
- When relaying a tool result, use its `message` field verbatim — don't invent text

### Notifier abstraction

`wasp/notifier.py` defines `Notifier` (Protocol), `TelegramNotifier`, `RecordingNotifier`. `watch_platform` is channel-agnostic — receives a `Notifier` instance. New channels add a `Notifier` implementation in `wasp/notifier.py`, injected from `provision.py`. Never put channel-specific logic in `watcher.py`.

`_select_notifier(channel)` routes by **channel of origin** (parsed from `session_id` prefix via `extract_channel`), not global env. `WASP_AGENT_NOTIFIER` overrides when set. Required because multiple channels coexist (Telegram + local-chat).

## Security

- User auth/authz via multi-channel allowlist (`auth_users`). See `docs/runbooks/auth-admin.md`.
- Active issues: `docs/security/issues/SEC-NNN-<slug>.md`. When resolved, move to `archived/`. Each has `id`, `severity`, `status`, `opened` (+ `resolved` when archived), description, impact, fix.
- Before reporting a security finding, check open issues for duplicates.

## External references

- agno: `docs/references/agno.md`
- Platform provisioning: `docs/architecture/platform-provisioning.md`
- Async watcher: `docs/architecture/async-watcher.md`

## Technical notes (bug-prevention session learnings)

### Telegram router has `/telegram` prefix

agno creates the `APIRouter` with `prefix="/telegram"`. Routes decorated `@router.post("/webhook", ...)` appear in `router.routes` with `path="/telegram/webhook"`, **not** `"/webhook"`. When inspecting/wrapping routes in `main.py`, match by suffix (`r.path.endswith("/webhook")`) or by `r.name == "telegram_webhook"` — never exact equality. Unit tests with `MagicMock(path="/webhook")` pass against broken implementations; include at least one test with the prefixed path.

### Webhook wrapper type annotations required

`webhook_with_auth` must have `request: Request` and `background_tasks: BackgroundTasks` annotated. Without annotations, FastAPI tries to resolve them as query params and returns 422 on every Telegram POST. Import `BackgroundTasks` from `starlette.background` inside `get_router_with_auth`. `Request` is already imported at the top of `wasp/clients/telegram/webhook.py` — `webhook_with_auth.__globals__` points to that module; don't reimport locally.

Regression covered by `test_webhook_with_auth_has_fastapi_type_annotations` via `inspect.signature`. Tests that call the endpoint directly don't catch this bug.

Python 3.14 + PEP 649: annotations in closures resolve via the module's `__globals__`, not the local scope. Importing `Request` inside `get_router_with_auth` is ineffective for FastAPI (ruff flags F401). Only import locally what's actually used in code.

### Test fixtures — `mock_agno` and OTEL

`tests/conftest.py` mocks `agno.models` as `MagicMock`. If `OTEL_EXPORTER_OTLP_ENDPOINT` is set in the shell, `configure()` calls `AgnoInstrumentor`, which does `from agno.models.base import Model` and fails against the mock. The fixture runs `monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)` — don't remove that line.

The `sys.modules.pop` loop in the fixture must include every `wasp.*` module created. When adding a new module in `wasp/`, add it to the fixture list, otherwise module state leaks between tests and causes intermittent failures.

When testing `telemetry.metrics_endpoint`, patch `wasp.telemetry.generate_latest` — not `prometheus_client.generate_latest`. The name is bound at import time; patching the source module doesn't affect the already-resolved name.

### E2E fixture — patch `_select_notifier`, not `TelegramNotifier`

In `tests/e2e/conftest.py`, `agent_client` patches `_select_notifier` directly:

```python
monkeypatch.setattr(wasp.provision, "_select_notifier", lambda *a, **kw: recording_notifier)
```

Patching only `TelegramNotifier` doesn't work: `WASP_AGENT_NOTIFIER=console` in `.env` is loaded by `load_dotenv()` in `main.py` at import, so `_select_notifier` returns `ConsoleNotifier` before reaching `TelegramNotifier`. The notifier goes to the console and `RecordingNotifier` never receives — test fails with `TimeoutError` and no clear error message.

The same fixture also monkeypatches `wasp.auth.is_authorized` to return a fake `user_id`:

```python
monkeypatch.setattr(wasp.auth, "is_authorized", lambda channel, channel_id: "e2e-user")
```

Without this, `session_id="tg:..."` hits the auth guard in `provision_platform_instance` and returns `{"status": "unauthorized"}` silently — the test fails downstream at Gitea's `get_file()` with 404, masking the real cause.

### ContextVar not inherited by threads

`chat_id_var` is a `ContextVar` defined in `wasp/logging.py`. `threading.Thread` does **not** inherit ContextVar from the parent thread — each thread starts with empty context. `watch_platform` runs in a separate thread and explicitly calls `chat_id_var.set(chat_id)` at the start. Any future function running in a new thread that needs `chat_id` must do the same.

### SQLite atomic check-then-write (`wasp/auth.py`)

Check-then-write operations (`redeem_invite`, `bootstrap_admin`) call `con.execute("BEGIN IMMEDIATE")` before the first SELECT to acquire the write lock immediately. After `BEGIN IMMEDIATE`, `sqlite3_get_autocommit()` returns 0, so the Python module doesn't auto-emit another `BEGIN` before the DML. The subsequent `with con:` closes the transaction with COMMIT (success) or ROLLBACK (exception). Early `return None` before `with con:` makes `con.close()` in `finally` roll back an empty transaction — no side effects.

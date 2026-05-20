# agno

- Minimum version: `agno>=2.0.0`. The 1.x API is different and incompatible.
- SQLite session: `db=SqliteDb(db_file=..., session_table=...)` via `agno.db.sqlite.sqlite`. `SqliteAgentStorage` does not exist.
- Context history: `add_history_to_context=True` (not `add_history_to_messages`).
- `SqliteDb` requires `sqlalchemy` — declare it as an explicit dependency.
- Before writing agno code, verify import paths in the installed package (`.venv/lib/`). Official docs often diverge from the installed version.
- `@tool` without `requires_confirmation`: the decorator now takes no arguments (`mocks["agno.tools"].tool = lambda fn: fn` in conftest). `requires_confirmation=True` is incompatible with Telegram — see `docs/architecture/platform-provisioning.md`.
- Decorator order with `@tool`: `@tool` must be the outermost decorator (applied last). Any inner decorator (e.g., `@tracer.start_as_current_span`, `@instrument`) must use `functools.wraps` — agno calls `inspect.signature()` which follows `__wrapped__` to the original function. Order: `@tool` → `@instrument` → `def fn`.
- agno has no pre-routing hook that exposes session context: `session_id` (and therefore channel/user_id) is only accessible inside a tool function via `run_context`. Starlette middleware added to the agno app cannot read agno session state before the tool is called.
- Telegram `session_id` format: `tg:<agent-name>:<chat_id>[:<message_short_id>]`. The optional 4th segment is a message hash, not the chat_id — extract chat_id via `parts[2]`, never `parts[-1]`.
- agno's AgentOS reserves `/metrics` and `/metrics/refresh` for its dashboard REST API. Appending a Starlette `Route("/metrics", ...)` is silently shadowed (first match wins). Mount Prometheus on a dedicated path (this project uses `/telemetry/prometheus`).
- REST API for agent runs: `POST /agents/{agent_id}/runs` with body `{"message": "...", "session_id": "..."}`. Reuse the same `session_id` on subsequent POSTs to continue a multi-turn conversation (the SqliteDb stores state by session). In tests, use `httpx.AsyncClient(app=app, base_url="http://test")` to call the app in-process without starting a real server.

For details and future-cycle checklists, see `docs/notes/2026-05-13-agno-api-cycle1.md`.

To run the bot locally with ngrok, see `docs/runbooks/telegram-local-dev.md`.
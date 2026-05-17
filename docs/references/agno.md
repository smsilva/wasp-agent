# agno

- Minimum version: `agno>=2.0.0`. The 1.x API is different and incompatible.
- SQLite session: `db=SqliteDb(db_file=..., session_table=...)` via `agno.db.sqlite.sqlite`. `SqliteAgentStorage` does not exist.
- Context history: `add_history_to_context=True` (not `add_history_to_messages`).
- `SqliteDb` requires `sqlalchemy` — declare it as an explicit dependency.
- Before writing agno code, verify import paths in the installed package (`.venv/lib/`). Official docs often diverge from the installed version.
- `@tool` without `requires_confirmation`: the decorator now takes no arguments (`mocks["agno.tools"].tool = lambda fn: fn` in conftest). `requires_confirmation=True` is incompatible with Telegram — see `docs/architecture/platform-provisioning.md`.

For details and future-cycle checklists, see `docs/notes/2026-05-13-agno-api-cycle1.md`.

To run the bot locally with ngrok, see `docs/runbooks/telegram-local-dev.md`.
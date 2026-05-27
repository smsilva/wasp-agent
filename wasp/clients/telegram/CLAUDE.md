# wasp/clients/telegram

## Router prefix `/telegram`

agno creates the `APIRouter` with `prefix="/telegram"`. Routes decorated `@router.post("/webhook", ...)` appear with `path="/telegram/webhook"`, **not** `"/webhook"`. When inspecting/wrapping routes in `main.py`, match by suffix (`r.path.endswith("/webhook")`) or by `r.name == "telegram_webhook"` — never exact equality. Unit tests with `MagicMock(path="/webhook")` pass against broken implementations; include at least one test with the prefixed path.

## Webhook wrapper type annotations

`webhook_with_auth` must have `request: Request` and `background_tasks: BackgroundTasks` annotated. Without annotations, FastAPI tries to resolve them as query params and returns 422 on every POST. Import `BackgroundTasks` from `starlette.background` inside `get_router_with_auth`. `Request` is already imported at the top of `webhook.py` — `webhook_with_auth.__globals__` points to that module; don't reimport locally.

Python 3.14 + PEP 649: annotations in closures resolve via the module's `__globals__`, not the local scope. Importing `Request` inside the factory function is ineffective for FastAPI (ruff flags F401).

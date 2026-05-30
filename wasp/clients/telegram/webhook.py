import wasp.auth as auth
import wasp.telemetry as telemetry
from starlette.requests import Request
from wasp.clients.telegram.notifier import TelegramNotifier

WELCOME_MESSAGE = "Welcome, {display_name}. You are authorized to use wasp-agent."
INVALID_INVITE_MESSAGE = (
    "Invalid or expired link. Request a new one from the administrator."
)


async def _process_start_token(payload: dict, redeem_fn, send_fn) -> bool:
    """Intercept ``/start <token>`` deep links.

    Returns ``True`` if the payload was handled (caller must short-circuit).
    Returns ``False`` to let agno process normally.
    """
    message = payload.get("message") or payload.get("edited_message") or {}
    text = (message.get("text") or "").strip()
    if not text.startswith("/start "):
        return False
    token = text.split(maxsplit=1)[1].split()[0]
    chat_id = message.get("chat", {}).get("id")
    if chat_id is None:
        return False
    result = redeem_fn(token, "tg", str(chat_id))
    if result is None:
        telemetry.auth_denied(channel="tg", reason="invalid_token")
        await send_fn(str(chat_id), INVALID_INVITE_MESSAGE)
    else:
        _user_id, display_name = result
        await send_fn(str(chat_id), WELCOME_MESSAGE.format(display_name=display_name))
    return True


def _install_start_token_handler(iface) -> None:
    """Wrap ``iface.get_router`` so ``/start <token>`` is intercepted.

    agno's built-in ``/start`` handler discards positional args. We wrap the
    ``/webhook`` route's endpoint so wasp can redeem invite tokens before
    agno dispatches the message to the LLM.
    """
    # NOTE: relies on agno's internal ``Telegram.get_router()`` API. If agno
    # changes this contract, this wrapper must be updated.
    original_get_router = iface.get_router
    notifier = TelegramNotifier(iface.token)

    def get_router_with_auth():
        from starlette.background import BackgroundTasks

        router = original_get_router()
        webhook_route = next(
            r for r in router.routes if getattr(r, "path", "").endswith("/webhook")
        )
        original_endpoint = webhook_route.endpoint

        async def webhook_with_auth(
            request: Request, background_tasks: BackgroundTasks
        ):
            from starlette.responses import JSONResponse
            from agno.os.interfaces.telegram.security import (
                validate_webhook_secret_token,
            )

            secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if not validate_webhook_secret_token(secret_token):
                return JSONResponse({"detail": "Invalid secret token"}, status_code=403)

            body = await request.json()
            handled = await _process_start_token(
                body, lambda *a: auth.get_repository().redeem_invite(*a), notifier.send
            )
            if handled:
                return JSONResponse({"status": "ok"})

            # Starlette's Request.json() caches `_json` on the instance after
            # first call; agno's downstream `await request.json()` reuses it.
            return await original_endpoint(request, background_tasks)

        webhook_route.endpoint = webhook_with_auth
        return router

    iface.get_router = get_router_with_auth

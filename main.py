import os

from dotenv import load_dotenv

load_dotenv()

from wasp.logging import configure_logging  # noqa: E402

configure_logging()

os.umask(0o077)  # agent.db created with 600 permissions

import wasp.telemetry as telemetry  # noqa: E402 — must come after load_dotenv so env vars are set

from agno.agent import Agent  # noqa: E402
from agno.os import AgentOS  # noqa: E402
from agno.os.interfaces.telegram import Telegram  # noqa: E402
from agno.db.sqlite.sqlite import SqliteDb  # noqa: E402
from wasp import auth, provision_platform_instance  # noqa: E402
auth.init_db()
from wasp.notifier import TelegramNotifier  # noqa: E402

INSTRUCTIONS = [
    "You are a DevOps assistant.",
    "You help engineers provision infrastructure resources, monitor their status,"
    " and receive notifications when resources become ready.",
    "Resources are managed via Crossplane on Kubernetes. When discussing resource"
    " state, refer to Crossplane conditions and status fields.",
    "Answer concisely and in the same language the user writes in."
    " Be direct and clear. No filler words ('Certo!', 'Pronto!', 'Perfeito!', 'Excelente!'),"
    " no emojis, no exclamation marks. Use short paragraphs separated by blank lines"
    " — avoid bullet lists and bold text unless structure genuinely helps.",
    "Never call provision_platform_instance without explicit user confirmation."
    " On the first turn of any creation or deletion request, always ask the user"
    " to confirm — e.g. 'Confirma a criação?' — and wait for an affirmative reply"
    " before calling any tool."
    " After a successful provisioning, relay the tool's message as-is —"
    " do not add technical details like commit SHA, file paths, or internal"
    " infrastructure names (ArgoCD, Crossplane, GitHub, Kubernetes).",
    "Currently, you can only create new tenants. Any other operation (update,"
    " delete, list, status) is not yet supported — acknowledge the request and"
    " let the user know it will be available in a future update.",
]


def _build_model():
    provider = os.getenv("LLM_PROVIDER", "ollama")
    if provider == "ollama":
        from agno.models.ollama import Ollama

        return Ollama(
            id=os.getenv("OLLAMA_MODEL", "llama3.1"),
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )
    if provider == "anthropic":
        from agno.models.anthropic import Claude

        return Claude(
            id=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
            auth_token=os.getenv("ANTHROPIC_AUTH_TOKEN"),
        )
    if provider == "openai":
        from agno.models.openai import OpenAIChat

        return OpenAIChat(
            id=os.getenv("OPENAI_MODEL", "gpt-4o"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
    raise ValueError(
        f"LLM_PROVIDER inválido: {provider!r}. Use: ollama, anthropic, openai"
    )


agent = Agent(
    name="wasp-agent",
    model=_build_model(),
    db=SqliteDb(db_file="agent.db", session_table="agent_sessions"),
    add_history_to_context=True,
    instructions=INSTRUCTIONS,
    tools=[provision_platform_instance],
)

WELCOME_MESSAGE = (
    "Bem-vindo, {display_name}. Você está autorizado a usar o wasp-agent."
)
INVALID_INVITE_MESSAGE = (
    "Link inválido ou expirado. Solicite um novo ao administrador."
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
    # `text.strip()` above guarantees non-whitespace follows the "/start "
    # prefix, so `split()` always yields at least one element.
    token = text.split(maxsplit=1)[1].split()[0]
    chat_id = message.get("chat", {}).get("id")
    if chat_id is None:
        return False
    result = redeem_fn(token, "tg", str(chat_id))
    if result is None:
        await send_fn(str(chat_id), INVALID_INVITE_MESSAGE)
    else:
        _user_id, display_name = result
        await send_fn(str(chat_id), WELCOME_MESSAGE.format(display_name=display_name))
    return True


def _install_start_token_handler(iface: Telegram) -> None:
    """Wrap ``iface.get_router`` so ``/start <token>`` is intercepted.

    agno's built-in ``/start`` handler discards positional args. We wrap the
    ``/webhook`` route's endpoint so wasp can redeem invite tokens before
    agno dispatches the message to the LLM.
    """
    # NOTE: relies on agno's internal `Telegram.get_router()` API. If agno
    # changes this contract, this wrapper must be updated.
    original_get_router = iface.get_router
    notifier = TelegramNotifier(iface.token)

    def get_router_with_auth():
        router = original_get_router()
        webhook_route = next(
            r for r in router.routes
            if getattr(r, "path", "").endswith("/webhook")
        )
        original_endpoint = webhook_route.endpoint

        async def webhook_with_auth(request, background_tasks):
            from starlette.responses import JSONResponse
            from agno.os.interfaces.telegram.security import (
                validate_webhook_secret_token,
            )

            secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if not validate_webhook_secret_token(secret_token):
                return JSONResponse(
                    {"detail": "Invalid secret token"}, status_code=403
                )

            body = await request.json()
            handled = await _process_start_token(
                body, auth.redeem_invite, notifier.send
            )
            if handled:
                return JSONResponse({"status": "ok"})

            # Starlette's Request.json() caches `_json` on the instance after
            # first call; agno's downstream `await request.json()` reuses it.
            return await original_endpoint(request, background_tasks)

        webhook_route.endpoint = webhook_with_auth
        return router

    iface.get_router = get_router_with_auth  # type: ignore[method-assign]


interfaces = []
telegram_token = os.getenv("TELEGRAM_TOKEN")
if telegram_token:
    telegram_interface = Telegram(agent=agent, token=telegram_token)
    _install_start_token_handler(telegram_interface)
    interfaces.append(telegram_interface)

agent_os = AgentOS(
    agents=[agent],
    interfaces=interfaces,
)

app = agent_os.get_app()

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import Response  # noqa: E402
from starlette.routing import Route  # noqa: E402


async def metrics_endpoint(request: Request) -> Response:
    registry = telemetry._prometheus_registry
    data = generate_latest(registry) if registry is not None else generate_latest()
    return Response(data, media_type=CONTENT_TYPE_LATEST)


app.routes.append(Route("/telemetry/prometheus", metrics_endpoint))

if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)

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
from wasp import provision_platform_instance  # noqa: E402

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

interfaces = []
telegram_token = os.getenv("TELEGRAM_TOKEN")
if telegram_token:
    interfaces.append(Telegram(agent=agent, token=telegram_token))

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

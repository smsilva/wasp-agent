import os

from dotenv import load_dotenv

load_dotenv()

os.umask(0o077)  # agent.db created with 600 permissions

from agno.agent import Agent  # noqa: E402
from agno.models.anthropic import Claude  # noqa: E402
from agno.os import AgentOS  # noqa: E402
from agno.os.interfaces.telegram import Telegram  # noqa: E402
from agno.db.sqlite.sqlite import SqliteDb  # noqa: E402
from tools import provision_platform_instance  # noqa: E402

INSTRUCTIONS = [
    "You are a DevOps assistant.",
    "You help engineers provision infrastructure resources, monitor their status,"
    " and receive notifications when resources become ready.",
    "Resources are managed via Crossplane on Kubernetes. When discussing resource"
    " state, refer to Crossplane conditions and status fields.",
    "Answer concisely and in the same language the user writes in.",
    "Always confirm resource creation or deletion before executing.",
    "When a capability is not yet available, acknowledge the request and let the"
    " user know it will be supported in a future update.",
]

agent = Agent(
    name="wasp-agent",
    model=Claude(id="bedrock/anthropic.claude-4-5-haiku"),
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

if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)

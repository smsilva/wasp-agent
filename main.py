import os

from dotenv import load_dotenv

load_dotenv()

from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.os import AgentOS
from agno.os.interfaces.telegram import Telegram
from agno.db.sqlite.sqlite import SqliteDb

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

interfaces = []
if os.getenv("TELEGRAM_TOKEN"):
    interfaces.append(Telegram(token=os.getenv("TELEGRAM_TOKEN")))

agent = Agent(
    name="wasp-agent",
    model=Claude(id="bedrock/anthropic.claude-4-5-haiku"),
    db=SqliteDb(db_file="agent.db", session_table="agent_sessions"),
    add_history_to_context=True,
    instructions=INSTRUCTIONS,
)

agent_os = AgentOS(
    agents=[agent],
    interfaces=interfaces,
)

app = agent_os.get_app()

if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)
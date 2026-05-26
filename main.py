from dotenv import load_dotenv

load_dotenv()

from wasp.startup import startup  # noqa: E402

startup()

import wasp.telemetry as telemetry  # noqa: E402
from agno.os import AgentOS  # noqa: E402
from wasp import auth  # noqa: E402
from wasp.agent import build_agent  # noqa: E402
from wasp.clients.interfaces import InterfaceLoader  # noqa: E402

auth.init_db()

agent = build_agent()

interfaces = InterfaceLoader(agent).build()

agent_os = AgentOS(
    agents=[agent],
    interfaces=interfaces,
)

app = agent_os.get_app()

telemetry.register_prometheus_route(app)

if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)

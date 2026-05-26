import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from wasp.logging import configure_logging  # noqa: E402

configure_logging()

from wasp.gitops_committer import GitOpsCommitter  # noqa: E402

try:
    GitOpsCommitter.probe()
except RuntimeError as e:
    logging.getLogger(__name__).error("startup: %s", e)
    sys.exit(1)

os.umask(0o077)  # agent.db created with 600 permissions

import wasp.telemetry as telemetry  # noqa: E402 — must come after load_dotenv so env vars are set

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

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

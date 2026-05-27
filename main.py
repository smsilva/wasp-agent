from dotenv import load_dotenv

load_dotenv()

# Ordering constraint (CLAUDE.md §23):
#   1. load_dotenv() above — must precede any `wasp.*` import, since
#      `wasp/__init__.py` triggers `wasp.telemetry.configure()` at import
#      time and configure() reads env vars.
#   2. startup() below — runs configure_logging(), os.umask(), and
#      GitOpsCommitter.probe() before the heavier imports (`agno.os`,
#      `wasp.agent`) so we fail fast and capture their logs.
from wasp.startup import startup  # noqa: E402

startup()

import asyncio
from contextlib import asynccontextmanager

import wasp.telemetry as telemetry  # noqa: E402
from agno.os import AgentOS  # noqa: E402
from wasp import auth  # noqa: E402
from wasp.agent import build_agent  # noqa: E402
from wasp.clients.interfaces import InterfaceLoader  # noqa: E402


def create_app():
    auth.init_db()
    agent = build_agent()
    loader = InterfaceLoader(agent)
    agent_os = AgentOS(
        agents=[agent],
        interfaces=loader.build(),
    )
    app = agent_os.get_app()
    telemetry.register_prometheus_route(app)
    discord_bot = loader.build_discord()
    if discord_bot is not None:
        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan_with_discord(app):
            task = asyncio.ensure_future(discord_bot.start_background())
            async with original_lifespan(app):
                yield
            task.cancel()
            await discord_bot.close()

        app.router.lifespan_context = lifespan_with_discord
    return app, agent_os


app, agent_os = create_app()


if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)

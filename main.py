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

from wasp import auth  # noqa: E402
from wasp.agent import build_agent  # noqa: E402
from wasp.clients.channels import ChannelLoader  # noqa: E402
import wasp.clients.telegram  # noqa: E402 F401 — registers TelegramChannel
import wasp.clients.discord  # noqa: E402 F401 — registers DiscordChannel


def create_app():
    auth.init_db()
    agent = build_agent()
    return ChannelLoader(agent).build_app()


app, agent_os = create_app()


if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)

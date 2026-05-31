import sys
from unittest.mock import MagicMock
import pytest


def pytest_collection_modifyitems(config, items):
    """Skip E2E tests unless -m e2e is explicitly requested."""
    if "e2e" not in config.option.markexpr:
        skip = pytest.mark.skip(
            reason="use 'pytest tests/e2e/ -m e2e --no-cov' to run E2E tests"
        )
        for item in items:
            if item.get_closest_marker("e2e"):
                item.add_marker(skip)


AGNO_MODULES = [
    "agno",
    "agno.agent",
    "agno.models",
    "agno.models.anthropic",
    "agno.models.ollama",
    "agno.models.openai",
    "agno.db",
    "agno.db.sqlite",
    "agno.db.sqlite.sqlite",
    "agno.db.postgres",
    "agno.os",
    "agno.os.interfaces",
    "agno.os.interfaces.telegram",
    "agno.os.interfaces.telegram.security",
    "agno.tools",
]

KUBE_MODULES = [
    "kubernetes",
    "kubernetes.client",
    "kubernetes.config",
]

DISCORD_MODULES = [
    "discord",
    "discord.ext",
    "discord.ext.commands",
]


@pytest.fixture(autouse=True)
def mock_agno(monkeypatch, request):
    if request.node.get_closest_marker("e2e"):
        yield {}
        return

    # Clear cached modules so each test gets a fresh import with current mocks.
    for mod in (
        "main",
        "wasp",
        "wasp.logging",
        "wasp.models",
        "wasp.agent",
        "wasp.sessions",
        "wasp.clients",
        "wasp.clients.channels",
        "wasp.clients.telegram",
        "wasp.clients.telegram.channel",
        "wasp.clients.telegram.notifier",
        "wasp.clients.telegram.webhook",
        "wasp.clients.k8s",
        "wasp.clients.k8s.reader",
        "wasp.clients.local",
        "wasp.clients.local.notifier",
        "wasp.clients.discord",
        "wasp.clients.discord.bot",
        "wasp.clients.discord.channel",
        "wasp.clients.discord.notifier",
        "wasp.provision",
        "wasp.watcher",
        "wasp.telemetry",
        "wasp.auth",
        "wasp.auth.protocol",
        "wasp.auth.sqlite_repository",
        "wasp.auth.postgres_repository",
        "wasp.auth._schema",
        "wasp.auth._connection",
        "wasp.auth_cli",
        "wasp.auth_guard",
        "wasp.gitops_committer",
        "wasp.resources",
        "wasp.resources.base",
        "wasp.resources.platform",
        "wasp.resources.platform.manifest",
        "wasp.resources.platform.inventory",
        "wasp.resources.platform.provisioner",
        "wasp.resources.protocol",
        "wasp.resources.registry",
        "wasp.resources.platform.provider",
        "wasp.startup",
    ):
        sys.modules.pop(mod, None)

    # Prevent AgnoInstrumentor from running: it imports agno.models.base at
    # instrument time, but agno.models is mocked as MagicMock below.
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    mocks = {
        name: MagicMock() for name in AGNO_MODULES + KUBE_MODULES + DISCORD_MODULES
    }
    for name, mock in mocks.items():
        monkeypatch.setitem(sys.modules, name, mock)
    # Make @tool a transparent no-op so provision_platform_instance remains directly callable in tests.
    mocks["agno.tools"].tool = lambda fn: fn

    # discord.Client must be a plain stub class (not a MagicMock subclass) so that
    # DiscordBot can subclass it without inheriting MagicMock's __getattr__ magic,
    # which tries to create child mocks of the same type and breaks __init__.
    # discord.Intents stays as a MagicMock instance so Intents.default() works via __getattr__.
    async def _stub_close(self) -> None:
        pass

    mocks["discord"].Client = type(
        "Client",
        (),
        {"user": None, "__init__": lambda self, **kw: None, "close": _stub_close},
    )
    # Prevent DISCORD_APP_TOKEN from leaking in from the shell environment so that
    # tests which don't explicitly set it don't accidentally create a DiscordBot.
    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)
    # Prevent load_dotenv() from reading the real .env during tests so that
    # monkeypatch.setenv/delenv has full control over env vars.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)

    # Channel registry is process-global; clear it so each test starts empty.
    # Use sys.modules.get to avoid triggering a fresh wasp import (which would
    # cache wasp.telemetry and break tests that need to import it themselves).
    _channels_setup = sys.modules.get("wasp.clients.channels")
    if _channels_setup is not None:
        _channels_setup.reset()
    # Auth repository singleton survives sys.modules.pop because test modules
    # hold a reference to the wasp.auth module object. Reset explicitly.
    _auth_setup = sys.modules.get("wasp.auth")
    if _auth_setup is not None:
        _auth_setup._reset_repository()
    yield mocks

    # Grab the live module object before evicting it so the reset call below
    # does not trigger a fresh import (which would cascade through wasp/__init__).
    _channels_teardown = sys.modules.get("wasp.clients.channels")
    _auth_teardown = sys.modules.get("wasp.auth")

    for mod in (
        "main",
        "wasp",
        "wasp.logging",
        "wasp.models",
        "wasp.agent",
        "wasp.sessions",
        "wasp.clients",
        "wasp.clients.channels",
        "wasp.clients.telegram",
        "wasp.clients.telegram.channel",
        "wasp.clients.telegram.notifier",
        "wasp.clients.telegram.webhook",
        "wasp.clients.k8s",
        "wasp.clients.k8s.reader",
        "wasp.clients.local",
        "wasp.clients.local.notifier",
        "wasp.clients.discord",
        "wasp.clients.discord.bot",
        "wasp.clients.discord.channel",
        "wasp.clients.discord.notifier",
        "wasp.provision",
        "wasp.watcher",
        "wasp.telemetry",
        "wasp.auth",
        "wasp.auth.protocol",
        "wasp.auth.sqlite_repository",
        "wasp.auth.postgres_repository",
        "wasp.auth._schema",
        "wasp.auth._connection",
        "wasp.auth_cli",
        "wasp.auth_guard",
        "wasp.gitops_committer",
        "wasp.resources",
        "wasp.resources.base",
        "wasp.resources.platform",
        "wasp.resources.platform.manifest",
        "wasp.resources.platform.inventory",
        "wasp.resources.platform.provisioner",
        "wasp.resources.protocol",
        "wasp.resources.registry",
        "wasp.resources.platform.provider",
        "wasp.startup",
    ):
        sys.modules.pop(mod, None)

    if _channels_teardown is not None:
        _channels_teardown.reset()
    if _auth_teardown is not None:
        _auth_teardown._reset_repository()

import sys
from unittest.mock import MagicMock
import pytest

AGNO_MODULES = [
    "agno",
    "agno.agent",
    "agno.models",
    "agno.models.anthropic",
    "agno.db",
    "agno.db.sqlite",
    "agno.db.sqlite.sqlite",
    "agno.os",
    "agno.os.interfaces",
    "agno.os.interfaces.telegram",
    "agno.tools",
]


@pytest.fixture(autouse=True)
def mock_agno(monkeypatch):
    # Clear cached modules so each test gets a fresh import with current mocks.
    for mod in ("main", "tools", "tools.provision"):
        sys.modules.pop(mod, None)

    mocks = {name: MagicMock() for name in AGNO_MODULES}
    for name, mock in mocks.items():
        monkeypatch.setitem(sys.modules, name, mock)
    # Make @tool(requires_confirmation=True) a transparent no-op so
    # provision_platform_instance remains directly callable in tests.
    mocks["agno.tools"].tool = lambda **kwargs: lambda fn: fn
    # Prevent load_dotenv() from reading the real .env during tests so that
    # monkeypatch.setenv/delenv has full control over env vars.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    yield mocks

    for mod in ("main", "tools", "tools.provision"):
        sys.modules.pop(mod, None)

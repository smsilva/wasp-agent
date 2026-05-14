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
]


@pytest.fixture(autouse=True)
def mock_agno(monkeypatch):
    mocks = {name: MagicMock() for name in AGNO_MODULES}
    for name, mock in mocks.items():
        monkeypatch.setitem(sys.modules, name, mock)
    sys.modules.pop("main", None)
    yield mocks
    sys.modules.pop("main", None)

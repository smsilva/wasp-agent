# Multi-channel Agent Cycle 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a working Telegram bot backed by an Agno Agent with SQLite session memory using Claude Haiku via LLM proxy.

**Architecture:** AgentOS (minimal FastAPI wrapper) manages a single Agent and Telegram interface. SQLite persists per-chat conversation history. All channel-specific logic lives in the `interfaces` list — the Agent core is untouched when new channels are added in future cycles.

**Tech Stack:** Python 3.12, uv, agno, python-dotenv, pytest, pytest-cov

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | uv project config, dependencies, coverage config |
| `Makefile` | `run`, `test`, `build` targets |
| `.env.example` | env var template for new contributors |
| `main.py` | Agent config, AgentOS setup, module-level `app` for uvicorn |
| `tests/__init__.py` | empty — marks `tests/` as a package |
| `tests/conftest.py` | mocks all agno modules to prevent real network/db calls in tests |
| `tests/test_main.py` | 3 unit tests for Agent and AgentOS configuration |

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `Makefile`
- Create: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "wasp-agent"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "agno>=1.4.0",
    "python-dotenv>=1.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.coverage.run]
omit = ["tests/*"]

[tool.coverage.report]
fail_under = 100
exclude_lines = [
    "if __name__ == .__main__.:",
]
```

- [ ] **Step 2: Install dependencies**

Run: `uv sync`
Expected: `uv.lock` created, `.venv/` populated with agno and dev deps.

- [ ] **Step 3: Create Makefile**

```makefile
.PHONY: run test build

run:
	uv run python main.py

test:
	uv run pytest --cov=. --cov-report=term-missing

build:
	uv sync
```

> Note: indent with a real tab character, not spaces — Make requires tabs.

- [ ] **Step 4: Create .env.example**

```
ANTHROPIC_BASE_URL=https://your-llm-proxy-url
ANTHROPIC_AUTH_TOKEN=your-auth-token
TELEGRAM_TOKEN=your-telegram-bot-token
```

- [ ] **Step 5: Update .gitignore**

Append to `.gitignore`:
```
agent.db
.env
.venv/
__pycache__/
.coverage
htmlcov/
dist/
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml Makefile .env.example .gitignore uv.lock
git commit -m "chore: scaffold uv project with deps and Makefile"
```

---

### Task 2: Write failing tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Create tests/__init__.py**

Empty file. Just create it:
```bash
touch tests/__init__.py
```

- [ ] **Step 2: Create tests/conftest.py**

This fixture mocks all agno modules before `main.py` is imported. Without this, importing `main` would try to connect to the LLM proxy and Telegram API.

```python
import sys
from unittest.mock import MagicMock
import pytest

AGNO_MODULES = [
    "agno",
    "agno.agent",
    "agno.models",
    "agno.models.anthropic",
    "agno.storage",
    "agno.storage.agent",
    "agno.storage.agent.sqlite",
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
```

- [ ] **Step 3: Create tests/test_main.py with all three tests**

```python
def test_agent_config(mock_agno):
    """Agent is instantiated with correct model, storage, history, and instructions."""
    import main

    mock_agno["agno.models.anthropic"].Claude.assert_called_once_with(
        id="bedrock/anthropic.claude-4-5-haiku"
    )
    mock_agno["agno.storage.agent.sqlite"].SqliteAgentStorage.assert_called_once_with(
        db_file="agent.db", table_name="agent_sessions"
    )
    call_kwargs = mock_agno["agno.agent"].Agent.call_args.kwargs
    assert call_kwargs["name"] == "wasp-agent"
    assert call_kwargs["add_history_to_messages"] is True
    assert "You are a DevOps assistant." in call_kwargs["instructions"]


def test_agent_os_with_token(mock_agno, monkeypatch):
    """AgentOS receives the agent and Telegram interface when TELEGRAM_TOKEN is set."""
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-token-123")

    import main

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_called_once_with(
        token="test-token-123"
    )
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert len(call_kwargs["interfaces"]) == 1


def test_telegram_not_added_without_token(mock_agno, monkeypatch):
    """No interfaces are added when TELEGRAM_TOKEN is absent."""
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    import main

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert call_kwargs["interfaces"] == []
```

- [ ] **Step 4: Run tests to confirm they fail**

Run: `uv run pytest tests/ -v`
Expected: `ModuleNotFoundError: No module named 'main'` — confirms tests are wired but implementation is missing.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: add failing tests for agent and AgentOS config"
```

---

### Task 3: Implement main.py

**Files:**
- Create: `main.py`

- [ ] **Step 1: Verify Agno import paths**

Before writing code, confirm these import paths in https://docs.agno.com/:
- `from agno.agent import Agent`
- `from agno.models.anthropic import Claude`
- `from agno.storage.agent.sqlite import SqliteAgentStorage`
- `from agno.os import AgentOS`
- `from agno.os.interfaces.telegram import Telegram`

If any path differs, update it in both `main.py` (Step 2 below) and `tests/conftest.py` (`AGNO_MODULES` list).

- [ ] **Step 2: Create main.py**

```python
import os

from dotenv import load_dotenv

load_dotenv()

from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.os import AgentOS
from agno.os.interfaces.telegram import Telegram
from agno.storage.agent.sqlite import SqliteAgentStorage

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
    storage=SqliteAgentStorage(db_file="agent.db", table_name="agent_sessions"),
    add_history_to_messages=True,
    instructions=INSTRUCTIONS,
)

agent_os = AgentOS(
    agents=[agent],
    interfaces=interfaces,
)

app = agent_os.get_app()

if __name__ == "__main__":  # pragma: no cover
    agent_os.serve(app="main:app", reload=True)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest --cov=. --cov-report=term-missing -v`
Expected: 3 PASSED, 100% coverage

If coverage fails for any line, check which line is uncovered and either add a test or verify the `exclude_lines` config in `pyproject.toml`.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(main): implement agent with Telegram interface and SQLite storage"
```

---

### Task 4: Smoke test (manual)

No code changes — manual verification only.

- [ ] **Step 1: Set up .env**

```bash
cp .env.example .env
```

Edit `.env` with real values:
- `ANTHROPIC_BASE_URL` — LLM proxy base URL
- `ANTHROPIC_AUTH_TOKEN` — LLM proxy auth token
- `TELEGRAM_TOKEN` — get from `@BotFather` on Telegram (`/newbot`)

- [ ] **Step 2: Run the agent**

Run: `make run`
Expected: AgentOS starts, Telegram long polling begins (log line mentioning Telegram or polling).

- [ ] **Step 3: Verify basic response**

Send any message to the bot on Telegram. Expected: bot replies concisely.

- [ ] **Step 4: Verify session memory**

Send two related messages in the same chat:
1. "My name is João."
2. "What's my name?"

Expected: second reply references "João" — confirms `add_history_to_messages=True` and SQLite storage are working.

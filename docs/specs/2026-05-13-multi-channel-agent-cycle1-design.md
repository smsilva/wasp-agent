# Multi-channel Agent — Cycle 1 Design

**Date:** 2026-05-13  
**Scope:** Telegram + Claude + SQLite, single agent, no tools. Validates the development cycle.

---

## Objective

Deploy a working Telegram bot backed by an Agno Agent that:
- Responds to user messages using `bedrock/anthropic.claude-4-5-haiku` via LLM proxy
- Persists conversation history per Telegram chat (session memory via SQLite)
- Establishes the ports-and-adapters architecture that later cycles will extend

---

## Architecture

Pattern: **ports-and-adapters (hexagonal)**, as defined in the brainstorming doc.

```
Telegram ──→ AgentOS (FastAPI) ──→ Agent core ──→ LLM proxy (Bedrock/Anthropic)
                                        │
                                   SQLite (agent.db)
```

The FastAPI server started by AgentOS is not used in this cycle but is the foundation for adding Discord and other channels without changing the core.

---

## Project Structure

```
wasp-agent/
├── pyproject.toml       # uv project (Python >=3.14); deps: agno, python-dotenv, pytest, pytest-cov
├── Makefile             # targets: run, build, test
├── .env.example         # template for required env vars
├── main.py              # single entrypoint
├── tests/
│   └── test_main.py
└── agent.db             # created at runtime (gitignored)
```

---

## Components

### Agent (core)

```python
Agent(
    name="wasp-agent",
    model=Claude(id="bedrock/anthropic.claude-4-5-haiku"),
    storage=SqliteAgentStorage(db_file="agent.db", table_name="agent_sessions"),
    add_history_to_messages=True,
    instructions=[...],  # see Instructions section
)
```

### Telegram interface

```python
Telegram(token=os.getenv("TELEGRAM_TOKEN"))
```

Added to `interfaces` only when `TELEGRAM_TOKEN` is set.

### AgentOS

```python
AgentOS(
    agents=[agent],
    interfaces=interfaces,
)
```

Serves via `agent_os.serve(app="main:app", reload=True)`.

---

## Agent Instructions

```
- You are a DevOps assistant.
- You help engineers provision infrastructure resources, monitor their status,
  and receive notifications when resources become ready.
- Resources are managed via Crossplane on Kubernetes. When discussing resource
  state, refer to Crossplane conditions and status fields.
- Answer concisely and in the same language the user writes in.
- Always confirm resource creation or deletion before executing.
- When a capability is not yet available, acknowledge the request and let the
  user know it will be supported in a future update.
```

---

## Environment Variables

| Variable               | Description                         |
|------------------------|-------------------------------------|
| `ANTHROPIC_BASE_URL`   | LLM proxy base URL                  |
| `ANTHROPIC_AUTH_TOKEN` | LLM proxy auth token                |
| `TELEGRAM_TOKEN`       | Telegram bot token (from BotFather) |

The Agno `Claude` model uses the Anthropic SDK, which respects these variables natively — no extra configuration in code.

---

## Session Identity

Agno's `Telegram` interface derives `session_id` from the Telegram `chat_id` automatically. Each chat has its own isolated history in SQLite.

---

## Makefile

| Target       | Description                                       |
|--------------|---------------------------------------------------|
| `make run`   | `uv run python main.py`                           |
| `make test`  | `uv run pytest --cov=. --cov-report=term-missing` |
| `make build` | `uv sync` (installs/updates all dependencies)     |

---

## Testing

Tool: `pytest --cov` (`pytest-cov` + `coverage.py`). Coverage threshold: 100%.

External integrations (Telegram API, LLM proxy) are mocked.

| Test | What it verifies |
|------|-----------------|
| `test_agent_config` | Agent is instantiated with correct model ID, SQLite storage, history enabled, and expected instructions |
| `test_agent_os_config` | AgentOS receives the agent and Telegram interface when `TELEGRAM_TOKEN` is set |
| `test_telegram_not_added_without_token` | No interfaces added when `TELEGRAM_TOKEN` is absent |

---

## How to Run

```bash
cp .env.example .env
# fill in ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, TELEGRAM_TOKEN
make run
```

---

## Out of Scope (Cycle 1)

- AG-UI / REST API usage
- Tools (MCP, Crossplane, EKS, AWS)
- Discord / Slack adapters
- Docker Compose / Postgres
- Multi-agent Team pattern

---

## Next Cycle

Cycle 2: add Discord adapter. Validates that the ports-and-adapters abstraction works with more than one channel — no changes to the Agent core.
# Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured JSON logging with configurable handlers (stdout + optional file), `chat_id` propagation via ContextVar, and OTel trace correlation via `LoggingInstrumentor`.

**Architecture:** New module `wasp/logging.py` owns all logging config (`JSONFormatter`, `chat_id_var`, `configure_logging()`). `main.py` replaces `basicConfig` with `configure_logging()`. `telemetry.configure()` wires `LoggingInstrumentor`. `provision.py` and `watcher.py` set `chat_id_var` at their async entry points.

**Tech Stack:** Python stdlib `logging`, `contextvars`, `json`; `opentelemetry-instrumentation-logging` (already in deps).

**Spec:** `docs/superpowers/specs/2026-05-23-logging-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `wasp/logging.py` | Create | `JSONFormatter`, `chat_id_var`, `configure_logging()` |
| `tests/test_logging.py` | Create | Unit tests for all of the above |
| `wasp/telemetry.py` | Modify | Add `LoggingInstrumentor().instrument()` in `configure()` |
| `tests/conftest.py` | Modify | Add `wasp.logging` to module cleanup list |
| `main.py` | Modify | Replace `basicConfig` with `configure_logging()` |
| `wasp/provision.py` | Modify | Import `chat_id_var`; set it at request entry; add `extra={"platform": name}` to key log calls |
| `wasp/watcher.py` | Modify | Import `chat_id_var`; set it at start of `watch_platform`; add `extra={"platform": name}` to key log calls |
| `.env.example` | Modify | Add logging variable section |

---

## Task 1: Create `wasp/logging.py` (TDD)

**Files:**
- Create: `wasp/logging.py`
- Create: `tests/test_logging.py`

### Step 1.1: Write failing tests for `JSONFormatter`

Create `tests/test_logging.py`:

```python
import json
import logging
import pytest


def make_record(msg="test message", name="wasp.test", level=logging.INFO, **extra):
    record = logging.LogRecord(
        name=name, level=level, pathname="", lineno=0,
        msg=msg, args=(), exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


def test_json_formatter_basic_fields():
    from wasp.logging import JSONFormatter
    formatter = JSONFormatter()
    output = json.loads(formatter.format(make_record()))
    assert output["level"] == "INFO"
    assert output["logger"] == "wasp.test"
    assert output["msg"] == "test message"
    assert "ts" in output


def test_json_formatter_ts_ends_with_z():
    from wasp.logging import JSONFormatter
    formatter = JSONFormatter()
    output = json.loads(formatter.format(make_record()))
    assert output["ts"].endswith("Z")


def test_json_formatter_chat_id_present_when_set():
    from wasp.logging import JSONFormatter, chat_id_var
    formatter = JSONFormatter()
    token = chat_id_var.set("5621932873")
    try:
        output = json.loads(formatter.format(make_record()))
        assert output["chat_id"] == "5621932873"
    finally:
        chat_id_var.reset(token)


def test_json_formatter_chat_id_absent_when_not_set():
    from wasp.logging import JSONFormatter, chat_id_var
    assert chat_id_var.get() is None
    formatter = JSONFormatter()
    output = json.loads(formatter.format(make_record()))
    assert "chat_id" not in output


def test_json_formatter_includes_trace_id_when_present():
    from wasp.logging import JSONFormatter
    formatter = JSONFormatter()
    record = make_record(otelTraceID="abc123def456", otelSpanID="00f067aa")
    output = json.loads(formatter.format(record))
    assert output["trace_id"] == "abc123def456"
    assert output["span_id"] == "00f067aa"


def test_json_formatter_omits_zero_trace_id():
    from wasp.logging import JSONFormatter
    formatter = JSONFormatter()
    record = make_record(otelTraceID="0", otelSpanID="0")
    output = json.loads(formatter.format(record))
    assert "trace_id" not in output
    assert "span_id" not in output


def test_json_formatter_omits_trace_id_when_absent():
    from wasp.logging import JSONFormatter
    formatter = JSONFormatter()
    output = json.loads(formatter.format(make_record()))
    assert "trace_id" not in output
    assert "span_id" not in output


def test_json_formatter_extra_field_platform():
    from wasp.logging import JSONFormatter
    formatter = JSONFormatter()
    record = make_record(platform="my-app")
    output = json.loads(formatter.format(record))
    assert output["platform"] == "my-app"


def test_configure_logging_default_has_one_stdout_handler(monkeypatch, tmp_path):
    monkeypatch.delenv("LOG_FILE", raising=False)
    monkeypatch.setenv("LOG_FORMAT", "text")
    from wasp.logging import configure_logging
    configure_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1


def test_configure_logging_json_stdout_uses_json_formatter(monkeypatch):
    from wasp.logging import configure_logging, JSONFormatter
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.delenv("LOG_FILE", raising=False)
    configure_logging()
    root = logging.getLogger()
    assert isinstance(root.handlers[0].formatter, JSONFormatter)


def test_configure_logging_text_stdout_uses_plain_formatter(monkeypatch):
    from wasp.logging import configure_logging, JSONFormatter
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.delenv("LOG_FILE", raising=False)
    configure_logging()
    root = logging.getLogger()
    assert not isinstance(root.handlers[0].formatter, JSONFormatter)


def test_configure_logging_file_handler_added_when_log_file_set(monkeypatch, tmp_path):
    log_file = str(tmp_path / "test.jsonl")
    monkeypatch.setenv("LOG_FILE", log_file)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    from wasp.logging import configure_logging
    configure_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 2


def test_configure_logging_file_handler_uses_json_formatter(monkeypatch, tmp_path):
    from wasp.logging import configure_logging, JSONFormatter
    log_file = str(tmp_path / "test.jsonl")
    monkeypatch.setenv("LOG_FILE", log_file)
    configure_logging()
    root = logging.getLogger()
    file_handler = root.handlers[1]
    assert isinstance(file_handler.formatter, JSONFormatter)


def test_configure_logging_independent_levels(monkeypatch, tmp_path):
    log_file = str(tmp_path / "test.jsonl")
    monkeypatch.setenv("LOG_FILE", log_file)
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LOG_FILE_LEVEL", "DEBUG")
    from wasp.logging import configure_logging
    configure_logging()
    root = logging.getLogger()
    stdout_handler = root.handlers[0]
    file_handler = root.handlers[1]
    assert stdout_handler.level == logging.WARNING
    assert file_handler.level == logging.DEBUG


def test_configure_logging_creates_parent_dirs(monkeypatch, tmp_path):
    log_file = str(tmp_path / "subdir" / "nested" / "test.jsonl")
    monkeypatch.setenv("LOG_FILE", log_file)
    from wasp.logging import configure_logging
    configure_logging()
    assert (tmp_path / "subdir" / "nested").is_dir()


def test_configure_logging_is_idempotent(monkeypatch):
    monkeypatch.delenv("LOG_FILE", raising=False)
    from wasp.logging import configure_logging
    configure_logging()
    configure_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1
```

- [ ] **Step 1.2: Run tests to verify they all fail**

```bash
cd /home/silvios/git/wasp-agent && uv run pytest tests/test_logging.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'wasp.logging'` (or similar import errors).

- [ ] **Step 1.3: Implement `wasp/logging.py`**

Create `wasp/logging.py`:

```python
import json
import logging
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

chat_id_var: ContextVar[str | None] = ContextVar("chat_id", default=None)

_BUILTIN_ATTRS = frozenset({
    "args", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs",
    "msg", "name", "pathname", "process", "processName", "relativeCreated",
    "stack_info", "taskName", "thread", "threadName",
    "otelTraceID", "otelSpanID", "otelServiceName", "otelTraceSampled",
})


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        chat_id = chat_id_var.get()
        if chat_id:
            obj["chat_id"] = chat_id

        trace_id = getattr(record, "otelTraceID", None)
        if trace_id and trace_id != "0":
            obj["trace_id"] = trace_id

        span_id = getattr(record, "otelSpanID", None)
        if span_id and span_id != "0":
            obj["span_id"] = span_id

        for key, val in record.__dict__.items():
            if key not in _BUILTIN_ATTRS:
                obj[key] = val

        return json.dumps(obj)


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO")
    fmt = os.getenv("LOG_FORMAT", "text")
    log_file = os.getenv("LOG_FILE")
    file_level = os.getenv("LOG_FILE_LEVEL", "DEBUG")

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    stdout_handler = logging.StreamHandler()
    stdout_handler.setLevel(level)
    if fmt == "json":
        stdout_handler.setFormatter(JSONFormatter())
    else:
        stdout_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
    root.addHandler(stdout_handler)

    if log_file:
        parent = os.path.dirname(log_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(file_level)
        file_handler.setFormatter(JSONFormatter())
        root.addHandler(file_handler)
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
cd /home/silvios/git/wasp-agent && uv run pytest tests/test_logging.py -v
```

Expected: all tests PASS.

- [ ] **Step 1.5: Check coverage**

```bash
cd /home/silvios/git/wasp-agent && uv run pytest tests/test_logging.py --cov=wasp.logging --cov-report=term-missing
```

Expected: 100% coverage on `wasp/logging.py`.

- [ ] **Step 1.6: Run ruff**

```bash
cd /home/silvios/git/wasp-agent && uv run ruff check wasp/logging.py tests/test_logging.py
```

Expected: no errors.

- [ ] **Step 1.7: Commit**

```bash
cd /home/silvios/git/wasp-agent && git add wasp/logging.py tests/test_logging.py
git commit -m "feat(logging): add JSONFormatter, chat_id_var, configure_logging"
```

---

## Task 2: Wire `LoggingInstrumentor` + update `conftest.py`

**Files:**
- Modify: `wasp/telemetry.py`
- Modify: `tests/conftest.py`

- [ ] **Step 2.1: Add `LoggingInstrumentor` to `telemetry.configure()`**

In `wasp/telemetry.py`, add at the very end of the `configure()` function (after the meter setup block, before the closing of the function):

```python
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    LoggingInstrumentor().instrument(set_logging_format=False)
```

The full end of `configure()` should look like:

```python
    # ... (existing meter setup) ...

    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    LoggingInstrumentor().instrument(set_logging_format=False)
```

- [ ] **Step 2.2: Add `wasp.logging` to module cleanup in `conftest.py`**

In `tests/conftest.py`, find the two loops that pop modules from `sys.modules`:

```python
    for mod in ("main", "wasp", "wasp.provision", "wasp.watcher", "wasp.telemetry"):
        sys.modules.pop(mod, None)
```

Change both occurrences to:

```python
    for mod in ("main", "wasp", "wasp.logging", "wasp.provision", "wasp.watcher", "wasp.telemetry"):
        sys.modules.pop(mod, None)
```

- [ ] **Step 2.3: Run full test suite to verify nothing broke**

```bash
cd /home/silvios/git/wasp-agent && uv run pytest tests/ --ignore=tests/e2e --ignore=tests/smoke -v
```

Expected: all tests PASS (same count as before Task 2).

- [ ] **Step 2.4: Check full coverage**

```bash
cd /home/silvios/git/wasp-agent && uv run pytest tests/ --ignore=tests/e2e --ignore=tests/smoke --cov=wasp --cov-report=term-missing
```

Expected: 100% — the new `LoggingInstrumentor().instrument()` line is covered by the existing `test_configure_noop_by_default` test which calls `telemetry.configure()`.

- [ ] **Step 2.5: Commit**

```bash
cd /home/silvios/git/wasp-agent && git add wasp/telemetry.py tests/conftest.py
git commit -m "feat(logging): wire LoggingInstrumentor in telemetry.configure"
```

---

## Task 3: Update `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 3.1: Replace `basicConfig` with `configure_logging()`**

In `main.py`, find:

```python
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

os.umask(0o077)  # agent.db created with 600 permissions

import wasp.telemetry as telemetry  # noqa: E402 — must come after load_dotenv so env vars are set
```

Replace with:

```python
import os

from dotenv import load_dotenv

load_dotenv()

from wasp.logging import configure_logging  # noqa: E402

configure_logging()

os.umask(0o077)  # agent.db created with 600 permissions

import wasp.telemetry as telemetry  # noqa: E402 — must come after load_dotenv so env vars are set
```

Note: `import logging` is no longer needed at the top of `main.py` (it was only there for `basicConfig`).

- [ ] **Step 3.2: Run test suite**

```bash
cd /home/silvios/git/wasp-agent && uv run pytest tests/ --ignore=tests/e2e --ignore=tests/smoke -v
```

Expected: all tests PASS.

- [ ] **Step 3.3: Run ruff**

```bash
cd /home/silvios/git/wasp-agent && uv run ruff check main.py
```

Expected: no errors.

- [ ] **Step 3.4: Commit**

```bash
cd /home/silvios/git/wasp-agent && git add main.py
git commit -m "feat(logging): replace basicConfig with configure_logging in main"
```

---

## Task 4: Set `chat_id_var` in `provision.py` and `watcher.py`

**Files:**
- Modify: `wasp/provision.py`
- Modify: `wasp/watcher.py`

- [ ] **Step 4.1: Update `provision.py`**

Add import at the top of `wasp/provision.py` (with the other wasp imports):

```python
from wasp.logging import chat_id_var
```

Find the block in `provision_platform_instance` where `chat_id` is extracted (around line 107):

```python
        chat_id = extract_chat_id(run_context)
        channel = extract_channel(run_context)
```

Change to:

```python
        chat_id = extract_chat_id(run_context)
        if chat_id:
            chat_id_var.set(chat_id)
        channel = extract_channel(run_context)
```

Add `extra={"platform": name}` to three key log calls in `provision_platform_instance`:

1. `log.info("Tenant %s already provisioning (manifest exists)", name)` → `log.info("Tenant %s already provisioning (manifest exists)", name, extra={"platform": name})`

2. `log.info("Watcher spawned for %s (chat_id=%s)", name, chat_id)` → `log.info("Watcher spawned for %s", name, extra={"platform": name})`

3. `log.exception("provision_platform_instance failed")` → `log.exception("provision_platform_instance failed", extra={"platform": name})`

- [ ] **Step 4.2: Update `watcher.py`**

Add import at the top of `wasp/watcher.py` (with the other wasp imports):

```python
from wasp.logging import chat_id_var
```

In `watch_platform`, add `chat_id_var.set(chat_id)` as the first line:

```python
async def watch_platform(
    name: str, chat_id: str, notifier: Notifier, parent_span_ctx=None
) -> None:
    chat_id_var.set(chat_id)
    log.info("Watcher started for %s", name)
    ...
```

Add `extra={"platform": name}` to key log calls in `_watch_platform_inner`:

- `log.info("Platform %s is Ready — notifying", name)` → `log.info("Platform %s is Ready — notifying", name, extra={"platform": name})`
- `log.warning("Watcher timeout for %s", name)` → `log.warning("Watcher timeout for %s", name, extra={"platform": name})`
- `log.exception("Watcher failed for %s", name)` → `log.exception("Watcher failed for %s", name, extra={"platform": name})`

- [ ] **Step 4.3: Run full test suite**

```bash
cd /home/silvios/git/wasp-agent && uv run pytest tests/ --ignore=tests/e2e --ignore=tests/smoke -v
```

Expected: all tests PASS. The existing tests cover the modified code paths (e.g., `test_provision_commits` exercises `provision_platform_instance`, `test_watcher.py` exercises `watch_platform`). No new tests needed for coverage since the lines are already hit.

- [ ] **Step 4.4: Check full coverage**

```bash
cd /home/silvios/git/wasp-agent && uv run pytest tests/ --ignore=tests/e2e --ignore=tests/smoke --cov=wasp --cov-report=term-missing
```

Expected: 100%.

- [ ] **Step 4.5: Run ruff**

```bash
cd /home/silvios/git/wasp-agent && uv run ruff check wasp/provision.py wasp/watcher.py
```

Expected: no errors.

- [ ] **Step 4.6: Commit**

```bash
cd /home/silvios/git/wasp-agent && git add wasp/provision.py wasp/watcher.py
git commit -m "feat(logging): propagate chat_id via ContextVar in provision and watcher"
```

---

## Task 5: Update `.env.example` + archive old specs

**Files:**
- Modify: `.env.example`
- Archive: `docs/sdlc/02-design/2026-05-16-structured-logging.md`
- Archive: `docs/sdlc/02-design/2026-05-20-persistent-audit-log.md`

- [ ] **Step 5.1: Add logging section to `.env.example`**

Add the following block after the existing `# PROMETHEUS_METRICS_ACTIVE=true` line in `.env.example`:

```bash
# Structured logging
# LOG_FORMAT=json         # stdout format: text (default) or json
# LOG_LEVEL=INFO          # stdout handler level (default: INFO)
# LOG_FILE=logs/wasp.jsonl  # JSONL file path; absent = no file handler
# LOG_FILE_LEVEL=DEBUG    # file handler level (default: DEBUG)
```

- [ ] **Step 5.2: Archive old specs**

Update `docs/sdlc/02-design/2026-05-16-structured-logging.md` — change `**Status:** Deferred` to `**Status:** Implemented` and add a note:

```markdown
**Status:** Implemented  
**Superseded by:** `docs/superpowers/specs/2026-05-23-logging-design.md`
```

Update `docs/sdlc/02-design/2026-05-20-persistent-audit-log.md` — change `**Status:** Idea` to `**Status:** Deferred` and add:

```markdown
**Status:** Deferred  
**Note:** Structured logging (LOG_FILE JSONL + OTel bridge) implemented in `docs/superpowers/specs/2026-05-23-logging-design.md`. OTLP export to persistent backend deferred.
```

Move both files to their archive directory:

```bash
cd /home/silvios/git/wasp-agent
mv docs/sdlc/02-design/2026-05-16-structured-logging.md docs/sdlc/02-design/archived/
mv docs/sdlc/02-design/2026-05-20-persistent-audit-log.md docs/sdlc/02-design/archived/
```

- [ ] **Step 5.3: Commit**

```bash
cd /home/silvios/git/wasp-agent && git add .env.example docs/sdlc/02-design/archived/
git commit -m "chore(logging): update env.example and archive superseded specs"
```

---

## Verification

After all tasks complete:

```bash
cd /home/silvios/git/wasp-agent && uv run pytest tests/ --ignore=tests/e2e --ignore=tests/smoke --cov=wasp --cov-report=term-missing && uv run ruff check .
```

Expected: 100% coverage, ruff clean.

Manual smoke: `LOG_FORMAT=json LOG_FILE=logs/wasp.jsonl make run` and verify `logs/wasp.jsonl` is written in JSONL, `jq . logs/wasp.jsonl` parses cleanly.

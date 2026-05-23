# Logging Design

**Date:** 2026-05-23  
**Status:** Approved  
**Replaces:** `docs/sdlc/02-design/2026-05-16-structured-logging.md`, `docs/sdlc/02-design/2026-05-20-persistent-audit-log.md`

## Goals

1. Local debuggability — structured output readable with `jq`.
2. Ephemeral audit trail in JSONL format compatible with future ingest (Loki, CloudWatch, OTLP log export).
3. Independent control of stdout and file output (format, level).

## Architecture

New module `wasp/logging.py` centralizes all logging configuration and replaces `logging.basicConfig` in `main.py`.

### Components

**`chat_id_var: ContextVar[str | None]`**  
Set at request entry in `provision.py`. Read by `JSONFormatter` to inject `chat_id` into every log record within that async context — no changes needed at `watcher.py` or `notifier.py` call sites.

**`JSONFormatter`**  
Reads `record.otelTraceID` and `record.otelSpanID` (injected by `LoggingInstrumentor`, already a project dependency). Reads `chat_id_var.get()`. Emits one JSON object per line.

**`configure_logging()`**  
Reads env vars, builds handlers, attaches them to the root logger. Called in `main.py` after `load_dotenv()` and before `telemetry.configure()`.

**`LoggingInstrumentor().instrument()`**  
Called inside `telemetry.configure()`. Patches Python `logging` to inject OTel trace context into every `LogRecord`. Already a declared dependency (`opentelemetry-instrumentation-logging`); only the call was missing.

### Handler setup

| Condition | Handler | Formatter |
|---|---|---|
| Always | stdout | text (`LOG_FORMAT=text`) or JSON (`LOG_FORMAT=json`) |
| `LOG_FILE` set | file | always JSON |

### Files changed

| File | Change |
|---|---|
| `wasp/logging.py` | new — `JSONFormatter`, `chat_id_var`, `configure_logging()` |
| `main.py` | remove `basicConfig`; call `configure_logging()` |
| `wasp/telemetry.py` | add `LoggingInstrumentor().instrument()` in `configure()` |
| `wasp/provision.py` | `chat_id_var.set(chat_id)` at request entry point |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Stdout handler level |
| `LOG_FORMAT` | `text` | Stdout format: `text` or `json` |
| `LOG_FILE` | (empty) | File path; absent = no file handler |
| `LOG_FILE_LEVEL` | `DEBUG` | File handler level (independent of `LOG_LEVEL`) |

## JSONL Format

```json
{"ts": "2026-05-23T10:00:00Z", "level": "INFO", "logger": "wasp.provision", "msg": "provision requested", "chat_id": "5621932873", "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "span_id": "00f067aa0ba902b7", "platform": "my-app"}
```

**Fixed fields:** `ts`, `level`, `logger`, `msg`.

**Conditional fields:**
- `chat_id` — omitted when `chat_id_var` has no value (e.g., startup logs).
- `trace_id` / `span_id` — omitted when no active OTel span.
- `platform` — passed via `extra={"platform": ...}` at relevant call sites in `provision.py` / `watcher.py`.

## Testing

- `tests/test_logging.py` (new): unit tests for `JSONFormatter` — verifies all fixed and conditional fields.
- `configure_logging()` coverage: verifies correct handlers are created for each env var combination (stdout-only text, stdout-only json, stdout+file).
- Existing fixtures (`conftest.py`) unchanged — `ContextVar` does not interfere with agno mocks.
- Coverage threshold: 100%.

## Out of scope

- OTLP log export (future-proof by format; `LoggingInstrumentor` is already wired for when a log exporter is added).
- Log rotation (delegate to `logrotate` or deployment environment).
- Persistent audit trail across restarts.

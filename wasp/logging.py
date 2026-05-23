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

        return json.dumps(obj, default=str)


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

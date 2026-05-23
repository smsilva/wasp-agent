import json
import logging


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

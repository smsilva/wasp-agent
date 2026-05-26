import pytest
from unittest.mock import MagicMock


def test_startup_configures_logging(mock_agno, monkeypatch):
    import wasp.startup as _startup

    spy = MagicMock()
    monkeypatch.setattr(_startup, "configure_logging", spy)
    monkeypatch.setattr(_startup.GitOpsCommitter, "probe", classmethod(MagicMock()))

    _startup.startup()

    spy.assert_called_once()


def test_startup_calls_probe(mock_agno, monkeypatch):
    import wasp.startup as _startup

    monkeypatch.setattr(_startup, "configure_logging", MagicMock())
    spy = MagicMock()
    monkeypatch.setattr(_startup.GitOpsCommitter, "probe", classmethod(spy))

    _startup.startup()

    spy.assert_called_once()


def test_startup_exits_on_probe_failure(mock_agno, monkeypatch):
    import wasp.startup as _startup

    monkeypatch.setattr(_startup, "configure_logging", MagicMock())
    monkeypatch.setattr(
        _startup.GitOpsCommitter,
        "probe",
        classmethod(MagicMock(side_effect=RuntimeError("bad token"))),
    )

    with pytest.raises(SystemExit) as exc_info:
        _startup.startup()

    assert exc_info.value.code == 1


def test_startup_sets_umask(mock_agno, monkeypatch):
    import wasp.startup as _startup

    monkeypatch.setattr(_startup, "configure_logging", MagicMock())
    monkeypatch.setattr(_startup.GitOpsCommitter, "probe", classmethod(MagicMock()))
    umask_spy = MagicMock(return_value=0)
    monkeypatch.setattr(_startup.os, "umask", umask_spy)

    _startup.startup()

    umask_spy.assert_called_once_with(0o077)

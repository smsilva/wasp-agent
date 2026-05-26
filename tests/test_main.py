def test_agent_os_with_token(mock_agno, monkeypatch):
    """AgentOS receives the agent and Telegram interface when TELEGRAM_TOKEN is set."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-token-123")

    import main  # noqa: F401

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_called_once_with(
        agent=mock_agno["agno.agent"].Agent.return_value,
        token="test-token-123",
    )
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert len(call_kwargs["interfaces"]) == 1


def test_telegram_not_added_without_token(mock_agno, monkeypatch):
    """No interfaces are added when TELEGRAM_TOKEN is absent."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    import main  # noqa: F401

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert call_kwargs["interfaces"] == []


def test_prometheus_route_registered(mock_agno, monkeypatch):
    """main.py delegates Prometheus route registration to telemetry."""
    from unittest.mock import MagicMock
    import wasp.telemetry as telemetry

    spy = MagicMock()
    monkeypatch.setattr(telemetry, "register_prometheus_route", spy)

    import main

    spy.assert_called_once_with(main.app)


def test_main_initializes_auth_db(mock_agno, monkeypatch):
    init_called = []
    monkeypatch.setattr(
        "wasp.auth.init_db", lambda db_file=None: init_called.append(db_file)
    )
    import main  # noqa: F401

    assert init_called


def test_install_start_token_handler_called_with_token(mock_agno, monkeypatch):
    """When TELEGRAM_TOKEN is set, the wrapper is installed on the interface."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tk")

    import main  # noqa: F401

    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    interface = call_kwargs["interfaces"][0]
    assert callable(interface.get_router)


def test_startup_called_on_import(mock_agno, monkeypatch):
    """main.py calls startup() during import."""
    from unittest.mock import MagicMock
    import wasp.startup as _startup

    spy = MagicMock()
    monkeypatch.setattr(_startup, "startup", spy)

    import main  # noqa: F401

    spy.assert_called_once()

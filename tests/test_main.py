def test_agent_os_with_telegram_token(mock_agno, monkeypatch):
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
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    import main  # noqa: F401

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert call_kwargs["interfaces"] == []


def test_prometheus_route_registered(mock_agno, monkeypatch):
    from unittest.mock import MagicMock
    import wasp.telemetry as telemetry

    spy = MagicMock()
    monkeypatch.setattr(telemetry, "register_prometheus_route", spy)

    import main

    spy.assert_called_once_with(main.app)


def test_main_initializes_auth_db(mock_agno, monkeypatch):
    init_called = []
    from wasp import auth

    repo = auth.get_repository()
    monkeypatch.setattr(repo, "init_schema", lambda: init_called.append(None))
    import main  # noqa: F401

    assert init_called


def test_install_start_token_handler_called_with_token(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tk")

    import main  # noqa: F401

    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    interface = call_kwargs["interfaces"][0]
    assert callable(interface.get_router)


def test_startup_called_on_import(mock_agno, monkeypatch):
    from unittest.mock import MagicMock
    import wasp.startup as _startup

    spy = MagicMock()
    monkeypatch.setattr(_startup, "startup", spy)

    import main  # noqa: F401

    spy.assert_called_once()


def test_discord_lifespan_wraps_app_when_token_set(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")

    import main

    lifespan_name = getattr(main.app.router.lifespan_context, "__name__", "")
    assert lifespan_name == "composed_lifespan"


def test_no_discord_lifespan_wrap_without_token(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)

    import main

    lifespan_name = getattr(main.app.router.lifespan_context, "__name__", "")
    assert lifespan_name != "composed_lifespan"


def test_create_app_returns_app_and_agent_os(mock_agno, monkeypatch):
    import main

    assert main.app is not None
    assert main.agent_os is mock_agno["agno.os"].AgentOS.return_value


def test_create_app_calls_restore_pending_watches(mock_agno, monkeypatch):
    from unittest.mock import MagicMock
    import wasp.watches as _watches

    spy = MagicMock()
    monkeypatch.setattr(_watches, "restore_pending_watches", spy)

    import main  # noqa: F401

    spy.assert_called_once()

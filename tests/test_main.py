import pytest


def test_agent_config(mock_agno, monkeypatch):
    """Agent is instantiated with correct model, storage, history, and instructions."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")

    import main  # noqa: F401

    mock_agno["agno.models.ollama"].Ollama.assert_called_once_with(
        id="test-model", host="http://localhost:11434"
    )
    mock_agno["agno.db.sqlite.sqlite"].SqliteDb.assert_called_once_with(
        db_file="agent.db", session_table="agent_sessions"
    )
    call_kwargs = mock_agno["agno.agent"].Agent.call_args.kwargs
    assert call_kwargs["name"] == "wasp-agent"
    assert call_kwargs["add_history_to_context"] is True
    assert "You are a DevOps assistant." in call_kwargs["instructions"]


def test_agent_uses_anthropic_model(mock_agno, monkeypatch):
    """Agent uses Claude when LLM_PROVIDER=anthropic."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")

    import main  # noqa: F401

    mock_agno["agno.models.anthropic"].Claude.assert_called_once_with(
        id="claude-test", auth_token="tok"
    )


def test_agent_uses_openai_model(mock_agno, monkeypatch):
    """Agent uses OpenAIChat when LLM_PROVIDER=openai."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    import main  # noqa: F401

    mock_agno["agno.models.openai"].OpenAIChat.assert_called_once_with(
        id="gpt-4o", api_key="sk-test", base_url=None
    )


def test_unknown_provider_raises(mock_agno, monkeypatch):
    """ValueError raised for unknown LLM_PROVIDER."""
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="LLM_PROVIDER inválido"):
        import main  # noqa: F401


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


def test_metrics_route_exists():
    import main
    appended = [call.args[0] for call in main.app.routes.append.call_args_list]
    paths = [r.path for r in appended if hasattr(r, "path")]
    assert "/telemetry/prometheus" in paths


async def test_metrics_endpoint_returns_prometheus_format():
    import main
    response = await main.metrics_endpoint(request=None)
    assert response.status_code == 200
    assert "text/plain" in response.media_type


async def test_metrics_endpoint_uses_prometheus_registry(monkeypatch):
    from unittest.mock import patch
    import prometheus_client
    fake_data = b"# HELP agent_tool_calls_total Tool invocations\nagent_tool_calls_total 1.0\n"
    with patch("prometheus_client.generate_latest", return_value=fake_data) as mock_gen:
        import main
        import wasp.telemetry as telemetry
        telemetry._prometheus_registry = prometheus_client.REGISTRY
        response = await main.metrics_endpoint(request=None)
    mock_gen.assert_called_once_with(prometheus_client.REGISTRY)
    assert response.body == fake_data

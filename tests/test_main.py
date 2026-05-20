def test_agent_config(mock_agno):
    """Agent is instantiated with correct model, storage, history, and instructions."""
    import main  # noqa: F401

    mock_agno["agno.models.anthropic"].Claude.assert_called_once_with(
        id="bedrock/anthropic.claude-4-5-haiku"
    )
    mock_agno["agno.db.sqlite.sqlite"].SqliteDb.assert_called_once_with(
        db_file="agent.db", session_table="agent_sessions"
    )
    call_kwargs = mock_agno["agno.agent"].Agent.call_args.kwargs
    assert call_kwargs["name"] == "wasp-agent"
    assert call_kwargs["add_history_to_context"] is True
    assert "You are a DevOps assistant." in call_kwargs["instructions"]


def test_agent_os_with_token(mock_agno, monkeypatch):
    """AgentOS receives the agent and Telegram interface when TELEGRAM_TOKEN is set."""
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

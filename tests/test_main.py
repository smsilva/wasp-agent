def test_agent_config(mock_agno):
    """Agent is instantiated with correct model, storage, history, and instructions."""
    import main

    mock_agno["agno.models.anthropic"].Claude.assert_called_once_with(
        id="bedrock/anthropic.claude-4-5-haiku"
    )
    mock_agno["agno.storage.agent.sqlite"].SqliteAgentStorage.assert_called_once_with(
        db_file="agent.db", table_name="agent_sessions"
    )
    call_kwargs = mock_agno["agno.agent"].Agent.call_args.kwargs
    assert call_kwargs["name"] == "wasp-agent"
    assert call_kwargs["add_history_to_messages"] is True
    assert "You are a DevOps assistant." in call_kwargs["instructions"]


def test_agent_os_with_token(mock_agno, monkeypatch):
    """AgentOS receives the agent and Telegram interface when TELEGRAM_TOKEN is set."""
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-token-123")

    import main

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_called_once_with(
        token="test-token-123"
    )
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert len(call_kwargs["interfaces"]) == 1


def test_telegram_not_added_without_token(mock_agno, monkeypatch):
    """No interfaces are added when TELEGRAM_TOKEN is absent."""
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    import main

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert call_kwargs["interfaces"] == []

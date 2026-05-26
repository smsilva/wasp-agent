def test_build_agent_uses_ollama_by_default(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")

    from wasp.agent import build_agent

    build_agent()

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


def test_build_agent_tools(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    from wasp.agent import build_agent

    build_agent()

    call_kwargs = mock_agno["agno.agent"].Agent.call_args.kwargs
    tool_names = {getattr(t, "__name__", None) for t in call_kwargs["tools"]}
    assert "list_platform_instances" in tool_names
    assert "provision_platform_instance" in tool_names


def test_build_agent_returns_agent_instance(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    from wasp.agent import build_agent

    result = build_agent()

    assert result is mock_agno["agno.agent"].Agent.return_value

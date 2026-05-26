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

    fake_data = (
        b"# HELP agent_tool_calls_total Tool invocations\nagent_tool_calls_total 1.0\n"
    )
    with patch("prometheus_client.generate_latest", return_value=fake_data) as mock_gen:
        import main
        import wasp.telemetry as telemetry

        telemetry._prometheus_registry = prometheus_client.REGISTRY
        response = await main.metrics_endpoint(request=None)
    mock_gen.assert_called_once_with(prometheus_client.REGISTRY)
    assert response.body == fake_data


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


def test_startup_exits_when_probe_raises(mock_agno, monkeypatch):
    """App exits with code 1 when GitOpsCommitter.probe raises RuntimeError."""
    from unittest.mock import MagicMock
    import pytest
    import wasp.gitops_committer as gc

    monkeypatch.setattr(
        gc.GitOpsCommitter,
        "probe",
        classmethod(
            MagicMock(
                side_effect=RuntimeError(
                    "GitHub token is invalid (HTTP 401): Bad credentials"
                )
            )
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        import main  # noqa: F401

    assert exc_info.value.code == 1


def test_startup_continues_when_probe_succeeds(mock_agno, monkeypatch):
    """App starts normally when probe returns without raising."""
    from unittest.mock import MagicMock
    import wasp.gitops_committer as gc

    spy = MagicMock(return_value=None)
    monkeypatch.setattr(gc.GitOpsCommitter, "probe", classmethod(spy))

    import main  # noqa: F401

    spy.assert_called_once()

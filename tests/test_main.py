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


async def test_start_token_redeems_invite_and_sends_welcome(mock_agno, monkeypatch):
    """/start <token> calls redeem_invite and replies with welcome message."""
    import main

    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    def fake_redeem(token, channel, channel_id):
        assert token == "ABC123"
        assert channel == "tg"
        assert channel_id == "42"
        return ("uid-1", "Alice")

    payload = {"message": {"text": "/start ABC123", "chat": {"id": 42}}}
    handled = await main._process_start_token(payload, fake_redeem, fake_send)

    assert handled is True
    assert sent == [
        ("42", "Bem-vindo, Alice. Você está autorizado a usar o wasp-agent.")
    ]


async def test_start_token_invalid_sends_error_message(mock_agno, monkeypatch):
    """When redeem_invite returns None, user receives generic error and metric is emitted."""
    import main
    import wasp.telemetry as telemetry

    sent = []
    denied = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    def fake_redeem(token, channel, channel_id):
        return None

    monkeypatch.setattr(telemetry, "auth_denied", lambda **kw: denied.append(kw))

    payload = {"message": {"text": "/start BAD", "chat": {"id": 7}}}
    handled = await main._process_start_token(payload, fake_redeem, fake_send)

    assert handled is True
    assert sent == [
        ("7", "Link inválido ou expirado. Solicite um novo ao administrador.")
    ]
    assert denied == [{"channel": "tg", "reason": "invalid_token"}]


async def test_start_without_token_is_not_handled(mock_agno, monkeypatch):
    """Bare /start (no positional arg) falls through to agno."""
    import main

    calls = []

    async def fake_send(chat_id, text):
        calls.append((chat_id, text))

    def fake_redeem(*args, **kwargs):
        calls.append(("redeem", args))
        return None

    payload = {"message": {"text": "/start", "chat": {"id": 1}}}
    handled = await main._process_start_token(payload, fake_redeem, fake_send)

    assert handled is False
    assert calls == []


async def test_non_start_message_is_not_handled(mock_agno, monkeypatch):
    """Regular messages fall through to agno."""
    import main

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "hello bot", "chat": {"id": 1}}}
    handled = await main._process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_start_token_handles_edited_message(mock_agno, monkeypatch):
    """`edited_message` is also inspected (Telegram delivers edits separately)."""
    import main

    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    def fake_redeem(token, channel, channel_id):
        return ("uid", "Bob")

    payload = {"edited_message": {"text": "/start XYZ", "chat": {"id": 5}}}
    handled = await main._process_start_token(payload, fake_redeem, fake_send)
    assert handled is True
    assert sent[0][0] == "5"


async def test_start_token_missing_chat_id_not_handled(mock_agno, monkeypatch):
    """Defensive: payload without chat.id is ignored."""
    import main

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "/start ABC", "chat": {}}}
    handled = await main._process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


def test_main_initializes_auth_db(mock_agno, monkeypatch):
    init_called = []
    monkeypatch.setattr(
        "wasp.auth.init_db", lambda db_file=None: init_called.append(db_file)
    )
    import main  # noqa: F401

    assert init_called  # init_db was called at import time


def test_install_start_token_handler_called_with_token(mock_agno, monkeypatch):
    """When TELEGRAM_TOKEN is set, the wrapper is installed on the interface."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tk")

    import main  # noqa: F401

    # _install_start_token_handler reassigns iface.get_router, so the interface
    # passed to AgentOS must NOT be the unmodified mock instance.
    call_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    interface = call_kwargs["interfaces"][0]
    # The wrapper replaces get_router with a plain function (not a MagicMock attr)
    assert callable(interface.get_router)


async def test_start_token_trailing_space_not_handled(mock_agno, monkeypatch):
    """`/start ` (trailing space, no token) falls through to agno without crashing."""
    import main

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "/start ", "chat": {"id": 1}}}
    handled = await main._process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_start_token_only_whitespace_not_handled(mock_agno, monkeypatch):
    """`/start    ` (only whitespace after command) falls through without crashing."""
    import main

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "/start   \t  ", "chat": {"id": 1}}}
    handled = await main._process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_install_start_token_handler_wraps_webhook(mock_agno, monkeypatch):
    """The installed get_router wraps the /webhook endpoint, intercepting /start tokens."""
    from unittest.mock import MagicMock, AsyncMock

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tk")
    monkeypatch.setenv("APP_ENV", "development")
    import main

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/webhook", endpoint=original_endpoint)
    status_route = MagicMock(path="/status", endpoint=MagicMock())
    fake_router = MagicMock(routes=[status_route, webhook_route])

    # A real-enough fake Telegram interface: has token + get_router method.
    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    main._install_start_token_handler(iface)

    monkeypatch.setattr(main.auth, "redeem_invite", lambda *a, **kw: ("uid", "Carol"))
    # APP_ENV=development makes validate_webhook_secret_token return True for any header.
    import sys

    sys.modules[
        "agno.os.interfaces.telegram.security"
    ].validate_webhook_secret_token = lambda token: True

    sent = []

    async def fake_send(self, chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(main.TelegramNotifier, "send", fake_send)

    router = iface.get_router()
    assert router is fake_router
    new_endpoint = webhook_route.endpoint
    assert new_endpoint is not original_endpoint

    # /start <token> path: handled, original endpoint NOT called.
    fake_request = MagicMock()
    fake_request.headers = {"X-Telegram-Bot-Api-Secret-Token": "ok"}
    fake_request.json = AsyncMock(
        return_value={"message": {"text": "/start ABC", "chat": {"id": 99}}}
    )
    background = MagicMock()
    response = await new_endpoint(fake_request, background)
    assert response.status_code == 200
    original_endpoint.assert_not_called()
    assert sent == [
        ("99", "Bem-vindo, Carol. Você está autorizado a usar o wasp-agent.")
    ]

    # Non-/start path: delegates to original. Starlette caches Request._json
    # automatically, so the wrapper does not need to replay request.json.
    fake_request2 = MagicMock()
    fake_request2.headers = {"X-Telegram-Bot-Api-Secret-Token": "ok"}
    fake_request2.json = AsyncMock(
        return_value={"message": {"text": "olá", "chat": {"id": 1}}}
    )
    result = await new_endpoint(fake_request2, background)
    assert result == "agno-result"
    original_endpoint.assert_awaited_once()


async def test_install_start_token_handler_finds_webhook_with_router_prefix(
    mock_agno, monkeypatch
):
    """agno's APIRouter prefixes routes with /telegram — wrapper must still locate /webhook."""
    from unittest.mock import MagicMock, AsyncMock

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tk")
    import main

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/telegram/webhook", endpoint=original_endpoint)
    status_route = MagicMock(path="/telegram/status", endpoint=MagicMock())
    fake_router = MagicMock(routes=[status_route, webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    main._install_start_token_handler(iface)
    iface.get_router()  # should not raise
    assert webhook_route.endpoint is not original_endpoint


async def test_webhook_rejects_missing_secret_token(mock_agno, monkeypatch):
    """A /start <token> POST without valid secret-token header gets 403 (no redeem call)."""
    from unittest.mock import MagicMock, AsyncMock

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tk")
    monkeypatch.delenv("APP_ENV", raising=False)
    import main

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/webhook", endpoint=original_endpoint)
    fake_router = MagicMock(routes=[webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    main._install_start_token_handler(iface)

    redeem_calls = []

    def fake_redeem(*args, **kwargs):
        redeem_calls.append(args)
        return ("uid", "Mallory")

    monkeypatch.setattr(main.auth, "redeem_invite", fake_redeem)
    # Force validator to fail (simulates missing/wrong header in production).
    import sys

    sys.modules[
        "agno.os.interfaces.telegram.security"
    ].validate_webhook_secret_token = lambda token: False

    iface.get_router()  # install wrapper
    new_endpoint = webhook_route.endpoint

    fake_request = MagicMock()
    fake_request.headers = {}  # missing secret token
    fake_request.json = AsyncMock(
        return_value={"message": {"text": "/start ABC", "chat": {"id": 99}}}
    )
    response = await new_endpoint(fake_request, MagicMock())

    assert response.status_code == 403
    assert redeem_calls == []
    original_endpoint.assert_not_called()


def test_agent_tools_include_list_platform_instances(mock_agno, monkeypatch):
    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("WASP_AGENT_ENABLE_TELEGRAM", "false")
    import main  # noqa: F401

    call_kwargs = mock_agno["agno.agent"].Agent.call_args.kwargs
    tool_names = {getattr(t, "__name__", None) for t in call_kwargs["tools"]}
    assert "list_platform_instances" in tool_names
    assert "provision_platform_instance" in tool_names


async def test_webhook_with_auth_has_fastapi_type_annotations(mock_agno, monkeypatch):
    """webhook_with_auth must have Request and BackgroundTasks type annotations.

    Without them FastAPI resolves the parameters as query params and returns
    422 Unprocessable Entity on every incoming webhook POST.
    """
    import inspect
    from unittest.mock import MagicMock, AsyncMock
    from starlette.requests import Request
    from starlette.background import BackgroundTasks

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tk")
    import main

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/telegram/webhook", endpoint=original_endpoint)
    fake_router = MagicMock(routes=[webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    main._install_start_token_handler(iface)
    iface.get_router()

    sig = inspect.signature(webhook_route.endpoint)
    params = sig.parameters
    assert params["request"].annotation is Request, (
        "Missing Request annotation — FastAPI will return 422 on every webhook POST"
    )
    assert params["background_tasks"].annotation is BackgroundTasks, (
        "Missing BackgroundTasks annotation — FastAPI will return 422 on every webhook POST"
    )

async def test_process_start_token_redeems_invite(mock_agno):
    from wasp.clients.telegram import _process_start_token

    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    def fake_redeem(token, channel, channel_id):
        assert token == "ABC123"
        assert channel == "tg"
        assert channel_id == "42"
        return ("uid-1", "Alice")

    payload = {"message": {"text": "/start ABC123", "chat": {"id": 42}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)

    assert handled is True
    assert sent == [("42", "Welcome, Alice. You are authorized to use wasp-agent.")]


async def test_process_start_token_invalid_sends_error(mock_agno, monkeypatch):
    import wasp.telemetry as telemetry
    from wasp.clients.telegram import _process_start_token

    sent = []
    denied = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    def fake_redeem(token, channel, channel_id):
        return None

    monkeypatch.setattr(telemetry, "auth_denied", lambda **kw: denied.append(kw))

    payload = {"message": {"text": "/start BAD", "chat": {"id": 7}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)

    assert handled is True
    assert sent == [
        ("7", "Invalid or expired link. Request a new one from the administrator.")
    ]
    assert denied == [{"channel": "tg", "reason": "invalid_token"}]


async def test_process_start_token_bare_start_not_handled(mock_agno):
    from wasp.clients.telegram import _process_start_token

    calls = []

    async def fake_send(chat_id, text):
        calls.append(("send", chat_id, text))

    def fake_redeem(*args, **kwargs):
        calls.append(("redeem", args))
        return None

    payload = {"message": {"text": "/start", "chat": {"id": 1}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)

    assert handled is False
    assert calls == []


async def test_process_start_token_non_start_not_handled(mock_agno):
    from wasp.clients.telegram import _process_start_token

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "hello bot", "chat": {"id": 1}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_process_start_token_edited_message(mock_agno):
    from wasp.clients.telegram import _process_start_token

    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    def fake_redeem(token, channel, channel_id):
        return ("uid", "Bob")

    payload = {"edited_message": {"text": "/start XYZ", "chat": {"id": 5}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is True
    assert sent[0][0] == "5"


async def test_process_start_token_missing_chat_id_not_handled(mock_agno):
    from wasp.clients.telegram import _process_start_token

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "/start ABC", "chat": {}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_process_start_token_trailing_space_not_handled(mock_agno):
    from wasp.clients.telegram import _process_start_token

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "/start ", "chat": {"id": 1}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_process_start_token_only_whitespace_not_handled(mock_agno):
    from wasp.clients.telegram import _process_start_token

    async def fake_send(chat_id, text):
        raise AssertionError("send should not be called")

    def fake_redeem(*args, **kwargs):
        raise AssertionError("redeem should not be called")

    payload = {"message": {"text": "/start   \t  ", "chat": {"id": 1}}}
    handled = await _process_start_token(payload, fake_redeem, fake_send)
    assert handled is False


async def test_install_start_token_handler_wraps_webhook(mock_agno, monkeypatch):
    from unittest.mock import MagicMock, AsyncMock
    import wasp.clients.telegram.webhook as telegram_mod
    from wasp.clients.telegram import _install_start_token_handler

    monkeypatch.setenv("APP_ENV", "development")

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/webhook", endpoint=original_endpoint)
    status_route = MagicMock(path="/status", endpoint=MagicMock())
    fake_router = MagicMock(routes=[status_route, webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    _install_start_token_handler(iface)

    monkeypatch.setattr(
        telegram_mod.auth, "redeem_invite", lambda *a, **kw: ("uid", "Carol")
    )
    import sys

    sys.modules[
        "agno.os.interfaces.telegram.security"
    ].validate_webhook_secret_token = lambda token: True

    sent = []

    async def fake_send(self, chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(telegram_mod.TelegramNotifier, "send", fake_send)

    router = iface.get_router()
    assert router is fake_router
    new_endpoint = webhook_route.endpoint
    assert new_endpoint is not original_endpoint

    fake_request = MagicMock()
    fake_request.headers = {"X-Telegram-Bot-Api-Secret-Token": "ok"}
    fake_request.json = AsyncMock(
        return_value={"message": {"text": "/start ABC", "chat": {"id": 99}}}
    )
    background = MagicMock()
    response = await new_endpoint(fake_request, background)
    assert response.status_code == 200
    original_endpoint.assert_not_called()
    assert sent == [("99", "Welcome, Carol. You are authorized to use wasp-agent.")]

    fake_request2 = MagicMock()
    fake_request2.headers = {"X-Telegram-Bot-Api-Secret-Token": "ok"}
    fake_request2.json = AsyncMock(
        return_value={"message": {"text": "olá", "chat": {"id": 1}}}
    )
    result = await new_endpoint(fake_request2, background)
    assert result == "agno-result"
    original_endpoint.assert_awaited_once()


async def test_install_start_token_handler_finds_webhook_with_router_prefix(mock_agno):
    from unittest.mock import MagicMock, AsyncMock
    from wasp.clients.telegram import _install_start_token_handler

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
    _install_start_token_handler(iface)
    iface.get_router()
    assert webhook_route.endpoint is not original_endpoint


async def test_webhook_rejects_missing_secret_token(mock_agno, monkeypatch):
    from unittest.mock import MagicMock, AsyncMock
    import wasp.clients.telegram.webhook as telegram_mod
    from wasp.clients.telegram import _install_start_token_handler

    monkeypatch.delenv("APP_ENV", raising=False)

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/webhook", endpoint=original_endpoint)
    fake_router = MagicMock(routes=[webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    _install_start_token_handler(iface)

    redeem_calls = []

    def fake_redeem(*args, **kwargs):
        redeem_calls.append(args)
        return ("uid", "Mallory")

    monkeypatch.setattr(telegram_mod.auth, "redeem_invite", fake_redeem)
    import sys

    sys.modules[
        "agno.os.interfaces.telegram.security"
    ].validate_webhook_secret_token = lambda token: False

    iface.get_router()
    new_endpoint = webhook_route.endpoint

    fake_request = MagicMock()
    fake_request.headers = {}
    fake_request.json = AsyncMock(
        return_value={"message": {"text": "/start ABC", "chat": {"id": 99}}}
    )
    response = await new_endpoint(fake_request, MagicMock())

    assert response.status_code == 403
    assert redeem_calls == []
    original_endpoint.assert_not_called()


async def test_webhook_with_auth_has_fastapi_type_annotations(mock_agno):
    import inspect
    from unittest.mock import MagicMock, AsyncMock
    from starlette.requests import Request
    from starlette.background import BackgroundTasks
    from wasp.clients.telegram import _install_start_token_handler

    original_endpoint = AsyncMock(return_value="agno-result")
    webhook_route = MagicMock(path="/telegram/webhook", endpoint=original_endpoint)
    fake_router = MagicMock(routes=[webhook_route])

    class FakeTelegram:
        def __init__(self):
            self.token = "tk"

        def get_router(self):
            return fake_router

    iface = FakeTelegram()
    _install_start_token_handler(iface)
    iface.get_router()

    sig = inspect.signature(webhook_route.endpoint)
    params = sig.parameters
    assert params["request"].annotation is Request, (
        "Missing Request annotation — FastAPI will return 422 on every webhook POST"
    )
    assert params["background_tasks"].annotation is BackgroundTasks, (
        "Missing BackgroundTasks annotation — FastAPI will return 422 on every webhook POST"
    )

from unittest.mock import MagicMock, patch


def test_build_returns_telegram_when_token_set(mock_agno, monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-123")
    from wasp.clients.interfaces import InterfaceLoader

    agent = MagicMock()
    with patch("wasp.clients.interfaces._install_start_token_handler"):
        result = InterfaceLoader(agent).build()

    assert len(result) == 1
    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_called_once_with(
        agent=agent, token="tok-123"
    )


def test_build_returns_empty_list_when_no_token(mock_agno, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    from wasp.clients.interfaces import InterfaceLoader

    agent = MagicMock()
    result = InterfaceLoader(agent).build()

    assert result == []
    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()


def test_build_installs_start_token_handler(mock_agno, monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-abc")
    from wasp.clients.interfaces import InterfaceLoader

    agent = MagicMock()
    with patch("wasp.clients.interfaces._install_start_token_handler") as mock_install:
        InterfaceLoader(agent).build()

    telegram_iface = mock_agno["agno.os.interfaces.telegram"].Telegram.return_value
    mock_install.assert_called_once_with(telegram_iface)


def test_build_discord_returns_bot_when_token_set(mock_agno, monkeypatch):
    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-token-123")
    from wasp.clients.interfaces import InterfaceLoader

    agent = MagicMock()
    loader = InterfaceLoader(agent)

    with patch("wasp.clients.interfaces.DiscordBot") as MockBot, \
         patch("wasp.clients.interfaces.DiscordNotifier") as MockNotifier:
        bot = loader.build_discord()

    MockNotifier.assert_called_once()
    MockBot.assert_called_once_with(agent=agent, notifier=MockNotifier.return_value)
    assert bot is MockBot.return_value


def test_build_discord_returns_none_when_no_token(mock_agno, monkeypatch):
    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)
    from wasp.clients.interfaces import InterfaceLoader

    agent = MagicMock()
    loader = InterfaceLoader(agent)
    bot = loader.build_discord()

    assert bot is None


def test_build_discord_stores_notifier_singleton(mock_agno, monkeypatch):
    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")
    from wasp.clients.interfaces import InterfaceLoader
    import wasp.clients.discord as dc_pkg

    agent = MagicMock()
    loader = InterfaceLoader(agent)

    with patch("wasp.clients.interfaces.DiscordBot"), \
         patch("wasp.clients.interfaces.DiscordNotifier") as MockNotifier:
        loader.build_discord()

    assert dc_pkg._notifier is MockNotifier.return_value

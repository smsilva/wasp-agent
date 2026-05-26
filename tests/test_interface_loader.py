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

    mock_install.assert_called_once()

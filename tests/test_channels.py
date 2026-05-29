import pytest
from unittest.mock import MagicMock


def test_register_and_get_returns_channel():
    from wasp.clients import channels

    ch = MagicMock(name="ch")
    ch.name = "fake"
    channels.register(ch)
    assert channels.get("fake") is ch


def test_get_returns_none_for_unknown_name():
    from wasp.clients import channels

    assert channels.get("missing") is None


def test_iter_channels_yields_registered_channels():
    from wasp.clients import channels

    a = MagicMock()
    a.name = "a"
    b = MagicMock()
    b.name = "b"
    channels.register(a)
    channels.register(b)
    assert set(channels.iter_channels()) == {a, b}


def test_register_overwrites_same_name():
    from wasp.clients import channels

    a = MagicMock()
    a.name = "x"
    b = MagicMock()
    b.name = "x"
    channels.register(a)
    channels.register(b)
    assert channels.get("x") is b
    assert list(channels.iter_channels()) == [b]


def test_reset_clears_registry():
    from wasp.clients import channels

    ch = MagicMock()
    ch.name = "x"
    channels.register(ch)
    channels.reset()
    assert channels.get("x") is None
    assert list(channels.iter_channels()) == []


def _fake_channel(
    name, *, enabled=True, interface=None, lifespan_cm=None, notifier=None
):
    ch = MagicMock()
    ch.name = name
    ch.enabled = MagicMock(return_value=enabled)
    ch.build_interface = MagicMock(return_value=interface)
    ch.lifespan = MagicMock(return_value=lifespan_cm)
    ch.notifier = MagicMock(return_value=notifier)
    return ch


def test_build_app_collects_interfaces_from_enabled_channels(mock_agno):
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    iface_a = MagicMock(name="iface_a")
    iface_b = MagicMock(name="iface_b")
    channels.register(_fake_channel("a", interface=iface_a))
    channels.register(_fake_channel("b", interface=iface_b))
    channels.register(_fake_channel("c", enabled=False, interface=MagicMock()))

    agent = MagicMock()
    ChannelLoader(agent).build_app()

    agent_os_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert agent_os_kwargs["agents"] == [agent]
    assert set(agent_os_kwargs["interfaces"]) == {iface_a, iface_b}


def test_build_app_returns_app_and_agent_os(mock_agno):
    from wasp.clients.channels import ChannelLoader

    app, agent_os = ChannelLoader(MagicMock()).build_app()

    agent_os_mock = mock_agno["agno.os"].AgentOS.return_value
    assert app is agent_os_mock.get_app.return_value
    assert agent_os is agent_os_mock


def test_build_app_registers_prometheus_route(mock_agno, monkeypatch):
    import wasp.telemetry as telemetry
    from wasp.clients.channels import ChannelLoader

    spy = MagicMock()
    monkeypatch.setattr(telemetry, "register_prometheus_route", spy)

    app, _ = ChannelLoader(MagicMock()).build_app()
    spy.assert_called_once_with(app)


def test_build_app_skips_channels_with_none_interface(mock_agno):
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    channels.register(_fake_channel("no-iface", interface=None))
    ChannelLoader(MagicMock()).build_app()

    agent_os_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert agent_os_kwargs["interfaces"] == []


def test_build_app_ignores_disabled_channels(mock_agno):
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    disabled = _fake_channel("off", enabled=False, interface=MagicMock())
    channels.register(disabled)
    ChannelLoader(MagicMock()).build_app()

    disabled.build_interface.assert_not_called()
    agent_os_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert agent_os_kwargs["interfaces"] == []


@pytest.mark.asyncio
async def test_build_app_wraps_lifespan_for_channels_that_provide_one(mock_agno):
    from contextlib import asynccontextmanager
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    enter_calls: list[str] = []
    exit_calls: list[str] = []

    @asynccontextmanager
    async def fake_channel_lifespan():
        enter_calls.append("ch")
        try:
            yield
        finally:
            exit_calls.append("ch")

    @asynccontextmanager
    async def original_lifespan(app):
        enter_calls.append("orig")
        try:
            yield
        finally:
            exit_calls.append("orig")

    # Force AgentOS.get_app() to return an app whose router lifespan we control.
    fake_app = MagicMock()
    fake_app.router.lifespan_context = original_lifespan
    mock_agno["agno.os"].AgentOS.return_value.get_app.return_value = fake_app

    channels.register(_fake_channel("dc", lifespan_cm=fake_channel_lifespan()))
    app, _ = ChannelLoader(MagicMock()).build_app()

    async with app.router.lifespan_context(app):
        pass

    assert enter_calls == ["ch", "orig"]
    assert exit_calls == ["orig", "ch"]


@pytest.mark.asyncio
async def test_build_app_does_not_wrap_lifespan_when_no_channel_provides_one(mock_agno):
    from contextlib import asynccontextmanager
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    @asynccontextmanager
    async def original_lifespan(app):
        yield

    fake_app = MagicMock()
    fake_app.router.lifespan_context = original_lifespan
    mock_agno["agno.os"].AgentOS.return_value.get_app.return_value = fake_app

    channels.register(_fake_channel("tg", lifespan_cm=None))
    app, _ = ChannelLoader(MagicMock()).build_app()

    assert app.router.lifespan_context is original_lifespan


@pytest.mark.asyncio
async def test_build_app_chains_multiple_channel_lifespans(mock_agno):
    from contextlib import asynccontextmanager
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    enter_calls: list[str] = []
    exit_calls: list[str] = []

    def make_cm(label):
        @asynccontextmanager
        async def cm():
            enter_calls.append(label)
            try:
                yield
            finally:
                exit_calls.append(label)

        return cm()

    @asynccontextmanager
    async def original_lifespan(app):
        enter_calls.append("orig")
        try:
            yield
        finally:
            exit_calls.append("orig")

    fake_app = MagicMock()
    fake_app.router.lifespan_context = original_lifespan
    mock_agno["agno.os"].AgentOS.return_value.get_app.return_value = fake_app

    channels.register(_fake_channel("a", lifespan_cm=make_cm("a")))
    channels.register(_fake_channel("b", lifespan_cm=make_cm("b")))
    app, _ = ChannelLoader(MagicMock()).build_app()

    async with app.router.lifespan_context(app):
        pass

    # Both channel CMs must enter before the original and exit after it.
    assert enter_calls[-1] == "orig"
    assert exit_calls[0] == "orig"
    assert set(enter_calls[:-1]) == {"a", "b"}
    assert set(exit_calls[1:]) == {"a", "b"}


def test_telegram_channel_name_is_tg():
    from wasp.clients.telegram.channel import TelegramChannel

    assert TelegramChannel().name == "tg"


def test_telegram_channel_enabled_when_token_set(monkeypatch):
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-123")
    assert TelegramChannel().enabled() is True


def test_telegram_channel_disabled_when_no_token(monkeypatch):
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    assert TelegramChannel().enabled() is False


def test_telegram_channel_build_interface_constructs_and_wraps(mock_agno, monkeypatch):
    from unittest.mock import patch
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-xyz")
    agent = MagicMock()
    with patch("wasp.clients.telegram.channel._install_start_token_handler") as install:
        iface = TelegramChannel().build_interface(agent)

    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_called_once_with(
        agent=agent, token="tok-xyz"
    )
    install.assert_called_once_with(iface)


def test_telegram_channel_build_interface_returns_none_without_token(
    mock_agno, monkeypatch
):
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    assert TelegramChannel().build_interface(MagicMock()) is None
    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()


def test_telegram_channel_lifespan_is_none():
    from wasp.clients.telegram.channel import TelegramChannel

    assert TelegramChannel().lifespan() is None


def test_telegram_channel_notifier_returns_telegram_notifier(monkeypatch):
    from wasp.clients.telegram.channel import TelegramChannel
    from wasp.clients.telegram import TelegramNotifier

    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-1")
    notifier = TelegramChannel().notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_telegram_channel_notifier_returns_none_without_token(monkeypatch):
    from wasp.clients.telegram.channel import TelegramChannel

    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    assert TelegramChannel().notifier() is None


def test_importing_telegram_package_registers_channel(monkeypatch):
    import sys
    from wasp.clients import channels

    # Importing channels may pull in wasp.clients.telegram transitively
    # (via watcher → provision). Reset the registry and evict the telegram
    # package so we can observe the registration side-effect in isolation.
    channels.reset()
    sys.modules.pop("wasp.clients.telegram", None)
    sys.modules.pop("wasp.clients.telegram.channel", None)

    assert channels.get("tg") is None
    import wasp.clients.telegram  # noqa: F401

    ch = channels.get("tg")
    assert ch is not None
    assert ch.name == "tg"


def test_discord_channel_name_is_dc():
    from wasp.clients.discord.channel import DiscordChannel

    assert DiscordChannel().name == "dc"


def test_discord_channel_enabled_when_token_set(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")
    assert DiscordChannel().enabled() is True


def test_discord_channel_disabled_when_no_token(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)
    assert DiscordChannel().enabled() is False


def test_discord_channel_build_interface_returns_none(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")
    assert DiscordChannel().build_interface(MagicMock()) is None


def test_discord_channel_notifier_returns_same_instance_twice(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel
    from wasp.clients.discord.notifier import DiscordNotifier

    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")
    ch = DiscordChannel()
    n1 = ch.notifier()
    n2 = ch.notifier()
    assert isinstance(n1, DiscordNotifier)
    assert n1 is n2


def test_discord_channel_notifier_returns_none_without_token(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)
    assert DiscordChannel().notifier() is None


@pytest.mark.asyncio
async def test_discord_channel_lifespan_starts_and_stops_bot(monkeypatch, mock_agno):
    import asyncio
    from unittest.mock import AsyncMock, patch
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.setenv("DISCORD_APP_TOKEN", "dc-tok")

    fake_bot = MagicMock()
    fake_bot.start_background = AsyncMock()
    fake_bot.close = AsyncMock()

    with patch("wasp.clients.discord.channel.DiscordBot", return_value=fake_bot):
        ch = DiscordChannel()
        ch._agent = MagicMock()  # set by build_interface in real flow; bypass here
        cm = ch.lifespan()
        assert cm is not None

        async with cm:
            await asyncio.sleep(0)

    fake_bot.close.assert_awaited_once()


def test_discord_channel_lifespan_is_none_without_token(monkeypatch):
    from wasp.clients.discord.channel import DiscordChannel

    monkeypatch.delenv("DISCORD_APP_TOKEN", raising=False)
    assert DiscordChannel().lifespan() is None


def test_importing_discord_package_registers_channel(monkeypatch):
    from wasp.clients import channels

    assert channels.get("dc") is None
    import wasp.clients.discord  # noqa: F401

    ch = channels.get("dc")
    assert ch is not None
    assert ch.name == "dc"


def test_discord_package_no_longer_exposes_notifier_singleton():
    import wasp.clients.discord as dc_pkg

    assert not hasattr(dc_pkg, "_notifier")

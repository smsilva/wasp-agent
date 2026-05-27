from unittest.mock import AsyncMock, MagicMock


async def test_discord_notifier_send_calls_channel_send():
    from wasp.clients.discord.notifier import DiscordNotifier

    channel = AsyncMock()
    notifier = DiscordNotifier()
    notifier.register("123456789", channel)
    await notifier.send("123456789", "hello")

    channel.send.assert_awaited_once_with("hello")


async def test_discord_notifier_send_unknown_user_is_silent():
    from wasp.clients.discord.notifier import DiscordNotifier

    notifier = DiscordNotifier()
    # must not raise
    await notifier.send("unknown_user", "hello")


async def test_discord_notifier_register_overwrites_channel():
    from wasp.clients.discord.notifier import DiscordNotifier

    channel1 = AsyncMock()
    channel2 = AsyncMock()
    notifier = DiscordNotifier()
    notifier.register("111", channel1)
    notifier.register("111", channel2)
    await notifier.send("111", "hi")

    channel2.send.assert_awaited_once_with("hi")
    channel1.send.assert_not_awaited()


async def test_discord_bot_on_message_authorized_calls_agent():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock(return_value=MagicMock(content="resposta"))
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = 111
    msg.author.name = "silvio"
    msg.content = "listar plataformas"
    msg.channel = AsyncMock()
    # bot.user is None on a bare instance — on_message checks msg.author != self.user
    # so we just need msg.author != bot.user (None != MagicMock() is True)

    monkeypatch_auth = MagicMock(return_value="user-001")

    import unittest.mock as mock
    with mock.patch.object(b.auth, "is_authorized", monkeypatch_auth):
        await bot.on_message(msg)

    agent.arun.assert_awaited_once()
    call_kwargs = agent.arun.call_args
    assert call_kwargs.args[0] == "listar plataformas"
    assert call_kwargs.kwargs["session_id"] == "dc:wasp-agent:111"
    msg.channel.send.assert_awaited_once()


async def test_discord_bot_on_message_ignores_own_messages():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock()
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    # Simulate bot.user by patching the property on the instance
    fake_user = MagicMock()
    import unittest.mock as mock
    with mock.patch.object(type(bot), "user", new_callable=lambda: property(lambda self: fake_user)):
        msg = MagicMock()
        msg.author = fake_user  # same object → own message
        msg.content = "hello"
        await bot.on_message(msg)

    agent.arun.assert_not_awaited()


async def test_discord_bot_on_message_unauthorized_user_is_silent():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock()
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = 999
    msg.author.name = "stranger"
    msg.content = "hello"
    msg.channel = AsyncMock()

    import unittest.mock as mock
    with mock.patch.object(b.auth, "is_authorized", return_value=None):
        await bot.on_message(msg)

    agent.arun.assert_not_awaited()
    msg.channel.send.assert_not_awaited()


async def test_discord_bot_registers_channel_on_authorized_message():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock(return_value=MagicMock(content="ok"))
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = 222
    msg.content = "ping"
    msg.channel = AsyncMock()

    import unittest.mock as mock
    with mock.patch.object(b.auth, "is_authorized", return_value="user-002"):
        await bot.on_message(msg)

    assert notifier._channels.get("222") is msg.channel


async def test_discord_bot_on_message_empty_content_is_ignored():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    agent.arun = AsyncMock()
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = 333
    msg.content = ""

    await bot.on_message(msg)

    agent.arun.assert_not_awaited()


async def test_discord_bot_start_background_calls_start_with_token():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    import unittest.mock as mock
    with mock.patch.object(bot, "start", new_callable=AsyncMock) as mock_start:
        with mock.patch.dict("os.environ", {"DISCORD_APP_TOKEN": "test-token"}):
            await bot.start_background()
        mock_start.assert_awaited_once_with("test-token")
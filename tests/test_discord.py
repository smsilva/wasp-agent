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

    mock_repo = MagicMock()
    mock_repo.is_authorized = MagicMock(return_value="user-001")

    import unittest.mock as mock

    with mock.patch.object(b.auth, "get_repository", return_value=mock_repo):
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

    with mock.patch.object(
        type(bot),
        "user",
        new_callable=lambda: property(lambda self: fake_user),
    ):
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

    mock_repo = MagicMock()
    mock_repo.is_authorized = MagicMock(return_value=None)

    with mock.patch.object(b.auth, "get_repository", return_value=mock_repo):
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

    mock_repo = MagicMock()
    mock_repo.is_authorized = MagicMock(return_value="user-002")

    with mock.patch.object(b.auth, "get_repository", return_value=mock_repo):
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


async def test_discord_notifier_set_loop_stores_loop():
    from wasp.clients.discord.notifier import DiscordNotifier
    import asyncio

    notifier = DiscordNotifier()
    loop = asyncio.get_event_loop()
    notifier.set_loop(loop)
    assert notifier._loop is loop


async def test_discord_notifier_send_crossloop_uses_run_coroutine_threadsafe():
    """When notifier._loop differs from the running loop, send bridges via run_coroutine_threadsafe."""
    from wasp.clients.discord.notifier import DiscordNotifier
    import asyncio
    import unittest.mock as mock

    channel = AsyncMock()
    notifier = DiscordNotifier()
    notifier.register("42", channel)

    fake_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    notifier.set_loop(fake_loop)

    future = MagicMock()
    future.result = MagicMock(return_value=None)

    with mock.patch("asyncio.run_coroutine_threadsafe", return_value=future) as rct:
        await notifier.send("42", "cross-loop message")

    rct.assert_called_once()
    future.result.assert_called_once()


async def test_discord_bot_on_ready_sets_loop_on_notifier():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier
    import asyncio

    agent = MagicMock()
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    await bot.on_ready()

    assert notifier._loop is asyncio.get_running_loop()


async def test_discord_bot_start_background_calls_start_with_token():
    import wasp.clients.discord.bot as b
    from wasp.clients.discord.notifier import DiscordNotifier

    agent = MagicMock()
    notifier = DiscordNotifier()
    bot = b.DiscordBot(agent=agent, notifier=notifier)

    import unittest.mock as mock

    with mock.patch.object(
        bot, "start", new_callable=AsyncMock, create=True
    ) as mock_start:
        with mock.patch.dict("os.environ", {"DISCORD_APP_TOKEN": "test-token"}):
            await bot.start_background()
        mock_start.assert_awaited_once_with("test-token")

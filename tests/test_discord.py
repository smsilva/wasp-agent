from unittest.mock import AsyncMock


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
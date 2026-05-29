from wasp.clients import channels
from wasp.clients.discord.bot import DiscordBot as DiscordBot
from wasp.clients.discord.channel import DiscordChannel as DiscordChannel
from wasp.clients.discord.notifier import DiscordNotifier as DiscordNotifier

if channels.get("dc") is None:
    channels.register(DiscordChannel())

from wasp.clients import channels
from wasp.clients.discord.bot import DiscordBot as DiscordBot
from wasp.clients.discord.channel import DiscordChannel as DiscordChannel
from wasp.clients.discord.notifier import DiscordNotifier as DiscordNotifier

channels.register(DiscordChannel())

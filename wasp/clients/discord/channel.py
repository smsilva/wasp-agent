import os
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from wasp.clients import Notifier
from wasp.clients.discord.bot import DiscordBot
from wasp.clients.discord.notifier import DiscordNotifier


class DiscordChannel:
    name = "dc"

    def __init__(self) -> None:
        self._agent = None
        self._notifier: DiscordNotifier | None = None

    def enabled(self) -> bool:
        return bool(os.getenv("DISCORD_APP_TOKEN"))

    def build_interface(self, agent):
        # Discord is not an agno Interface — capture the agent for lifespan().
        self._agent = agent
        return None

    def lifespan(self) -> AbstractAsyncContextManager | None:
        if not self.enabled():
            return None

        notifier = self.notifier()
        bot = DiscordBot(agent=self._agent, notifier=notifier)

        @asynccontextmanager
        async def discord_lifespan():
            import asyncio

            task = asyncio.ensure_future(bot.start_background())
            try:
                yield
            finally:
                task.cancel()
                await bot.close()

        return discord_lifespan()

    def notifier(self) -> Notifier | None:
        if not os.getenv("DISCORD_APP_TOKEN"):
            return None
        if self._notifier is None:
            self._notifier = DiscordNotifier()
        return self._notifier

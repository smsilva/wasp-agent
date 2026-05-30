import asyncio
import logging
import os

import discord

import wasp.auth as auth

log = logging.getLogger(__name__)

AGENT_NAME = "wasp-agent"


class DiscordBot(discord.Client):
    def __init__(self, *, agent, notifier) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self._agent = agent
        self._notifier = notifier

    async def on_ready(self) -> None:
        self._notifier.set_loop(asyncio.get_running_loop())

    async def on_message(self, message) -> None:
        if message.author == self.user:
            return
        if not message.content:
            return

        user_id = str(message.author.id)
        if auth.get_repository().is_authorized("dc", user_id) is None:
            return

        self._notifier.register(user_id, message.channel)
        session_id = f"dc:{AGENT_NAME}:{user_id}"
        result = await self._agent.arun(message.content, session_id=session_id)
        await message.channel.send(result.content)

    async def start_background(self) -> None:
        token = os.getenv("DISCORD_APP_TOKEN", "")
        await self.start(token)

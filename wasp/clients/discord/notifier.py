import asyncio
import logging

log = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self) -> None:
        self._channels: dict = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def register(self, user_id: str, channel) -> None:
        self._channels[user_id] = channel

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def send(self, chat_id: str, text: str) -> None:
        channel = self._channels.get(chat_id)
        if channel is None:
            log.debug("DiscordNotifier: no channel registered for chat_id=%s", chat_id)
            return
        loop = self._loop
        if loop is not None and loop != asyncio.get_running_loop():
            # watcher runs in a different asyncio loop; bridge to the discord loop
            future = asyncio.run_coroutine_threadsafe(channel.send(text), loop)
            await asyncio.get_running_loop().run_in_executor(None, future.result)
        else:
            await channel.send(text)

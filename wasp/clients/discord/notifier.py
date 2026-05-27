import logging

log = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self) -> None:
        self._channels: dict = {}

    def register(self, user_id: str, channel) -> None:
        self._channels[user_id] = channel

    async def send(self, user_id: str, text: str) -> None:
        channel = self._channels.get(user_id)
        if channel is None:
            log.debug("DiscordNotifier: no channel registered for user_id=%s", user_id)
            return
        await channel.send(text)

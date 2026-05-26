import logging

log = logging.getLogger(__name__)


class ConsoleNotifier:
    async def send(self, chat_id: str, text: str) -> None:
        log.info("[NOTIFIER chat_id=%s] %s", chat_id, text)

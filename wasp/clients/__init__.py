from typing import Protocol


class Notifier(Protocol):
    async def send(self, chat_id: str, text: str) -> None: ...

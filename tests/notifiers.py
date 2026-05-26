import asyncio


class RecordingNotifier:
    def __init__(self):
        self.messages: list[dict] = []

    async def send(self, chat_id: str, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})

    async def wait_for_message(self) -> None:
        while not self.messages:
            await asyncio.sleep(0.1)

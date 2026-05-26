import httpx


class TelegramNotifier:
    def __init__(self, token: str, base_url: str = "https://api.telegram.org"):
        self._token = token
        self._base_url = base_url

    async def send(self, chat_id: str, text: str) -> None:
        url = f"{self._base_url}/bot{self._token}/sendMessage"
        async with httpx.AsyncClient(timeout=10.0) as http:
            await http.post(url, json={"chat_id": chat_id, "text": text})

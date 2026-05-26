import os

from agno.os.interfaces.telegram import Telegram

from wasp.clients.telegram import _install_start_token_handler


class InterfaceLoader:
    def __init__(self, agent) -> None:
        self._agent = agent

    def build(self) -> list[Telegram]:
        builders = [self._build_telegram]
        return [iface for b in builders if (iface := b()) is not None]

    def _build_telegram(self) -> Telegram | None:
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            return None
        iface = Telegram(agent=self._agent, token=token)
        _install_start_token_handler(iface)
        return iface

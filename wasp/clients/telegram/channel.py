import os
from contextlib import AbstractAsyncContextManager

from wasp.clients import Notifier
from wasp.clients.telegram.notifier import TelegramNotifier
from wasp.clients.telegram.webhook import _install_start_token_handler


class TelegramChannel:
    name = "tg"

    def enabled(self) -> bool:
        return bool(os.getenv("TELEGRAM_TOKEN"))

    def build_interface(self, agent):
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            return None
        from agno.os.interfaces.telegram import Telegram

        iface = Telegram(agent=agent, token=token)
        _install_start_token_handler(iface)
        return iface

    def lifespan(self) -> AbstractAsyncContextManager | None:
        return None

    def notifier(self) -> Notifier | None:
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            return None
        return TelegramNotifier(token=token)

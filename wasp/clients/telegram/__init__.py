from wasp.clients import channels
from wasp.clients.telegram.channel import TelegramChannel as TelegramChannel
from wasp.clients.telegram.notifier import TelegramNotifier as TelegramNotifier
from wasp.clients.telegram.webhook import (
    _install_start_token_handler as _install_start_token_handler,
)
from wasp.clients.telegram.webhook import _process_start_token as _process_start_token

channels.register(TelegramChannel())

import logging

import wasp.telemetry as telemetry
from wasp import auth

log = logging.getLogger(__name__)

TRUSTED_CHANNELS = {"local"}


class AuthorizationGuard:
    def check(
        self, channel: str | None, chat_id: str | None, span
    ) -> tuple[str | None, dict | None]:
        if channel is None:
            return None, None

        span.set_attribute("auth.channel", channel)

        if channel in TRUSTED_CHANNELS:
            user_id = "local-operator"
            span.set_attribute("user.id", user_id)
            return user_id, None

        user_id = auth.is_authorized(channel, chat_id) if chat_id else None
        if user_id is None:
            log.warning("auth denied: channel=%s channel_id=%s", channel, chat_id)
            telemetry.auth_denied(channel=channel, reason="unknown_identity")
            return None, {"status": "unauthorized", "message": "Acesso negado."}

        span.set_attribute("user.id", user_id)
        return user_id, None

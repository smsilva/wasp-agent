import logging

from opentelemetry import trace

from wasp.auth_guard import AuthorizationGuard
from wasp.clients.k8s import KubernetesResourceReader
from wasp.resources.platform.manifest import (
    PLATFORM_GROUP,
    PLATFORM_PLURAL,
    PLATFORM_VERSION,
)
from wasp.watcher import extract_channel, extract_chat_id

log = logging.getLogger(__name__)


def _status_from_conditions(platform: dict) -> str:
    for c in platform.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return "Ready" if c.get("status") == "True" else "Pending"
    return "Unknown"


class PlatformInventory:
    def __init__(
        self,
        guard: AuthorizationGuard,
        reader: KubernetesResourceReader,
    ):
        self._guard = guard
        self._reader = reader

    @classmethod
    def from_env(cls) -> "PlatformInventory":
        return cls(
            guard=AuthorizationGuard(),
            reader=KubernetesResourceReader.from_env(),
        )

    def list(self, run_context) -> dict:
        span = trace.get_current_span()
        channel = extract_channel(run_context)
        chat_id = extract_chat_id(run_context)

        user_id, err = self._guard.check(channel, chat_id, span)
        if err is not None:
            return err

        try:
            items = self._reader.search_for_instance_of(
                PLATFORM_GROUP, PLATFORM_VERSION, PLATFORM_PLURAL
            )
            tenants = [
                {"name": i["metadata"]["name"], "status": _status_from_conditions(i)}
                for i in items
            ]
            return {"status": "ok", "tenants": tenants}
        except Exception:
            log.exception("list_platform_instances failed")
            return {
                "status": "error",
                "message": "List failed. Please try again later.",
            }

import logging
from datetime import datetime

from opentelemetry import trace

from wasp.auth_guard import AuthorizationGuard
from wasp.clients.k8s import KubernetesResourceReader
from wasp.resources.cluster.manifest import (
    CLUSTER_GROUP,
    CLUSTER_PLURAL,
    CLUSTER_VERSION,
)
from wasp.watcher import extract_channel, extract_chat_id

log = logging.getLogger(__name__)


def _status_from_conditions(cluster: dict) -> str:
    for c in cluster.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return "Ready" if c.get("status") == "True" else "Pending"
    return "Unknown"


def _ready_condition(cluster: dict) -> dict | None:
    for c in cluster.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return c
    return None


def _format_transition_date(condition: dict | None) -> str | None:
    if condition is None:
        return None
    ts = condition.get("lastTransitionTime")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d/%m")
    except ValueError:
        return None


def _status_message(name: str, status: str, condition: dict | None) -> str:
    date = _format_transition_date(condition)
    if date:
        return f"O Cluster {name} está {status} desde {date}."
    return f"O Cluster {name} está {status}."


class ClusterInventory:
    def __init__(
        self,
        guard: AuthorizationGuard,
        reader: KubernetesResourceReader,
    ):
        self._guard = guard
        self._reader = reader

    @classmethod
    def from_env(cls) -> "ClusterInventory":
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
                CLUSTER_GROUP, CLUSTER_VERSION, CLUSTER_PLURAL
            )
            clusters = [
                {"name": i["metadata"]["name"], "status": _status_from_conditions(i)}
                for i in items
            ]
            return {"status": "ok", "clusters": clusters}
        except Exception:
            log.exception("list_cluster_instances failed")
            return {
                "status": "error",
                "message": "List failed. Please try again later.",
            }

    def get(self, name: str, run_context) -> dict:
        span = trace.get_current_span()
        channel = extract_channel(run_context)
        chat_id = extract_chat_id(run_context)

        user_id, err = self._guard.check(channel, chat_id, span)
        if err is not None:
            return err

        try:
            item = self._reader.get_by_name(
                CLUSTER_GROUP, CLUSTER_VERSION, CLUSTER_PLURAL, name
            )
            if item is None:
                return {
                    "status": "not_found",
                    "name": name,
                    "message": f"Nenhum Cluster encontrado com o nome {name}.",
                }
            status = _status_from_conditions(item)
            condition = _ready_condition(item)
            return {
                "status": status,
                "name": name,
                "message": _status_message(name, status, condition),
            }
        except Exception:
            log.exception("get_cluster_status failed")
            return {
                "status": "error",
                "message": "Status check failed. Please try again later.",
            }

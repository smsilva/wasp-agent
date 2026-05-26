from wasp.watcher import (
    PLATFORM_GROUP,
    PLATFORM_PLURAL,
    PLATFORM_VERSION,
    load_kube_config_auto,
)


class PlatformClusterReader:
    def __init__(self, api):
        self._api = api

    @classmethod
    def from_env(cls) -> "PlatformClusterReader":
        return cls(api=load_kube_config_auto())

    def list_with_status(self) -> list[dict]:
        result = self._api.list_cluster_custom_object(
            group=PLATFORM_GROUP,
            version=PLATFORM_VERSION,
            plural=PLATFORM_PLURAL,
        )
        return [
            {
                "name": item["metadata"]["name"],
                "status": _status_from_conditions(item),
            }
            for item in result.get("items", [])
        ]


def _status_from_conditions(platform: dict) -> str:
    for c in platform.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return "Ready" if c.get("status") == "True" else "Pending"
    return "Unknown"

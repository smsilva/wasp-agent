from kubernetes.client import CustomObjectsApi

from wasp.clients.k8s import load_kube_config_auto


class KubernetesResourceReader:
    def __init__(self, api: CustomObjectsApi):
        self._api = api

    @classmethod
    def from_env(cls) -> "KubernetesResourceReader":
        return cls(api=load_kube_config_auto())

    def search_for_instance_of(
        self, group: str, version: str, plural: str
    ) -> list[dict]:
        result = self._api.list_cluster_custom_object(
            group=group, version=version, plural=plural
        )
        return result.get("items", [])

    def get_by_name(
        self, group: str, version: str, plural: str, name: str
    ) -> dict | None:
        try:
            return self._api.get_cluster_custom_object(
                group=group, version=version, plural=plural, name=name
            )
        except Exception as e:
            if getattr(e, "status", None) == 404:
                return None
            raise

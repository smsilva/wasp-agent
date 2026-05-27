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

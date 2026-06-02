from pydantic import BaseModel

from wasp.resources.base import MetadataSpec, ResourceManifest

CLUSTER_GROUP = "wasp.silvios.me"
CLUSTER_VERSION = "v1alpha1"
CLUSTER_PLURAL = "clusters"

DEFAULT_KUBERNETES_VERSION = "1.34"


class ClusterSpec(BaseModel):
    kubernetesVersion: str = DEFAULT_KUBERNETES_VERSION


class ClusterManifest(ResourceManifest):
    kind: str = "Cluster"
    spec: ClusterSpec

    @classmethod
    def build(
        cls, name: str, kubernetes_version: str = DEFAULT_KUBERNETES_VERSION
    ) -> "ClusterManifest":
        return cls(
            metadata=MetadataSpec(name=name),
            spec=ClusterSpec(kubernetesVersion=kubernetes_version),
        )

from collections.abc import Callable

from wasp.provision import (
    get_cluster_status,
    list_cluster_instances,
    provision_cluster_instance,
)


class ClusterProvider:
    name = "cluster"

    def tools(self) -> list[Callable]:
        return [
            provision_cluster_instance,
            list_cluster_instances,
            get_cluster_status,
        ]

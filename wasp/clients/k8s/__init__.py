from kubernetes import client, config


def load_kube_config_auto() -> "client.CustomObjectsApi":
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CustomObjectsApi()


from wasp.clients.k8s.reader import (  # noqa: E402
    KubernetesResourceReader as KubernetesResourceReader,
)

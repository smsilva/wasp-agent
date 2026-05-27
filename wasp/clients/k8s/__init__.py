from kubernetes import client, config


def load_kube_config_auto() -> "client.CustomObjectsApi":
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CustomObjectsApi()


# Re-export below must follow load_kube_config_auto: reader.py imports it
# from this module, so it must already exist in the package namespace.
from wasp.clients.k8s.reader import (  # noqa: E402
    KubernetesResourceReader as KubernetesResourceReader,
)

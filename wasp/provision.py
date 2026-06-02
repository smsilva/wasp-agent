from agno.tools import tool

import wasp.telemetry as telemetry
from wasp.resources.platform import (
    DEFAULT_DOMAIN,
    DEFAULT_REGIONS,
    PlatformInventory,
    PlatformProvisioner,
)
from wasp.resources.cluster import (
    DEFAULT_KUBERNETES_VERSION,
    ClusterInventory,
    ClusterProvisioner,
)


@tool
@telemetry.instrument("get_platform_status")
def get_platform_status(name: str, run_context=None) -> dict:
    """
    Returns the current status of a specific Platform instance.
    Returns: {"status": "Ready"|"Pending"|"Unknown"|"not_found", "name": str, "message": str}.
    Read-only — safe to call without confirmation.
    """
    return PlatformInventory.from_env().get(name=name, run_context=run_context)


@tool
@telemetry.instrument("list_platform_instances")
def list_platform_instances(run_context=None) -> dict:
    """
    Lists all provisioned platform instances and their cluster status.
    Returns: {"status": "ok", "tenants": [{"name": str, "status": "Ready"|"Pending"|"Unknown"}, ...]}.
    Read-only — safe to call without confirmation.
    """
    return PlatformInventory.from_env().list(run_context=run_context)


@tool
@telemetry.instrument("provision_platform_instance")
def provision_platform_instance(
    name: str,
    domain: str = DEFAULT_DOMAIN,
    regions: list[str] | None = None,
    requested_by: str = "",
    run_context=None,
) -> dict:
    """
    Provisions a new Platform instance by committing a Kubernetes manifest to a Git repository.

    Returns: status (provisioning|already_provisioning|unauthorized|error) + message.
    """
    if regions is None:
        regions = list(DEFAULT_REGIONS)
    return PlatformProvisioner.from_env().provision(
        name=name,
        domain=domain,
        regions=regions,
        requested_by=requested_by,
        run_context=run_context,
    )


@tool
@telemetry.instrument("get_cluster_status")
def get_cluster_status(name: str, run_context=None) -> dict:
    """
    Returns the current status of a specific Cluster instance.
    Returns: {"status": "Ready"|"Pending"|"Unknown"|"not_found", "name": str, "message": str}.
    Read-only — safe to call without confirmation.
    """
    return ClusterInventory.from_env().get(name=name, run_context=run_context)


@tool
@telemetry.instrument("list_cluster_instances")
def list_cluster_instances(run_context=None) -> dict:
    """
    Lists all provisioned Cluster instances and their status.
    Returns: {"status": "ok", "clusters": [{"name": str, "status": "Ready"|"Pending"|"Unknown"}, ...]}.
    Read-only — safe to call without confirmation.
    """
    return ClusterInventory.from_env().list(run_context=run_context)


@tool
@telemetry.instrument("provision_cluster_instance")
def provision_cluster_instance(
    name: str,
    kubernetes_version: str = DEFAULT_KUBERNETES_VERSION,
    requested_by: str = "",
    run_context=None,
) -> dict:
    """
    Provisions a new Cluster instance by committing a Kubernetes manifest to a Git repository.

    Returns: status (provisioning|already_provisioning|unauthorized|error) + message.
    """
    return ClusterProvisioner.from_env().provision(
        name=name,
        kubernetes_version=kubernetes_version,
        requested_by=requested_by,
        run_context=run_context,
    )

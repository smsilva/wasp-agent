from agno.tools import tool

import wasp.telemetry as telemetry
from wasp.resources.platform import (
    DEFAULT_DOMAIN,
    DEFAULT_REGIONS,
    PlatformInventory,
    PlatformProvisioner,
)


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
    Provisions a new Platform by committing a Crossplane manifest to
    smsilva/wasp-gitops. ArgoCD picks it up automatically.

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

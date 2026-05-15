import os

import yaml
from agno.tools import tool
from github import Github
from pydantic import BaseModel, Field

DEFAULT_DOMAIN = "wasp.silvios.me"
DEFAULT_REGIONS = ["us-east-1"]


class ServiceSpec(BaseModel):
    name: str


class RegionSpec(BaseModel):
    name: str
    endpoint: str


class PlatformSpec(BaseModel):
    domain: str
    regions: list[RegionSpec]
    services: list[ServiceSpec] = Field(
        default_factory=lambda: [
            ServiceSpec(name=s)
            for s in ["auth", "discovery", "callback", "portal"]
        ]
    )


class PlatformManifest(BaseModel):
    apiVersion: str = "wasp.silvios.me/v1alpha1"
    kind: str = "Platform"
    name: str
    spec: PlatformSpec

    @classmethod
    def build(cls, name: str, domain: str, regions: list[str]) -> "PlatformManifest":
        return cls(
            name=name,
            spec=PlatformSpec(
                domain=domain,
                regions=[
                    RegionSpec(
                        name=r,
                        endpoint=f"gateway.{r}.{name}.{domain}",
                    )
                    for r in regions
                ],
            ),
        )


@tool(requires_confirmation=True)
def provision_platform_instance(
    name: str,
    domain: str = DEFAULT_DOMAIN,
    regions: list[str] = DEFAULT_REGIONS,
    requested_by: str = "",
) -> dict:
    """
    Provisions a new Platform by committing a Crossplane manifest to
    smsilva/wasp-gitops. ArgoCD picks it up automatically.

    Returns: commit_sha, file_path, status.
    """
    pat = os.getenv("GH_PAT")
    if not pat:
        raise ValueError("GH_PAT environment variable is required")

    manifest = PlatformManifest.build(name=name, domain=domain, regions=regions)
    yaml_content = yaml.dump(manifest.model_dump(), default_flow_style=False, sort_keys=False)

    repo = Github(pat).get_repo("smsilva/wasp-gitops")
    file_path = f"infrastructure/tenants/{name}.yaml"
    commit_message = f"feat(tenants): provision {name}\n\nRequested by: {requested_by}"

    result = repo.create_file(
        path=file_path,
        message=commit_message,
        content=yaml_content,
        branch="dev",
    )

    return {
        "commit_sha": result["commit"].sha,
        "file_path": file_path,
        "status": "provisioning",
        "message": "Commit feito. ArgoCD vai sincronizar em ~1min.",
    }

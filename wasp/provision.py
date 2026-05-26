import logging

import wasp.telemetry as telemetry
import yaml
from agno.tools import tool
from opentelemetry import trace
from pydantic import BaseModel, Field
from wasp.auth_guard import AuthorizationGuard
from wasp.gitops_committer import GitOpsCommitter
from wasp.watcher import PlatformWatcherSpawner, extract_channel, extract_chat_id

log = logging.getLogger(__name__)

DEFAULT_DOMAIN = "wasp.silvios.me"
DEFAULT_REGIONS = ("us-east-1",)


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
            ServiceSpec(name=s) for s in ["auth", "discovery", "callback", "portal"]
        ]
    )


class MetadataSpec(BaseModel):
    name: str


class PlatformManifest(BaseModel):
    apiVersion: str = "wasp.silvios.me/v1alpha1"
    kind: str = "Platform"
    metadata: MetadataSpec
    spec: PlatformSpec

    @classmethod
    def build(cls, name: str, domain: str, regions: list[str]) -> "PlatformManifest":
        return cls(
            metadata=MetadataSpec(name=name),
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


class PlatformProvisioner:
    def __init__(
        self,
        guard: AuthorizationGuard,
        watcher_spawner: PlatformWatcherSpawner,
    ):
        self._guard = guard
        self._watcher_spawner = watcher_spawner

    @classmethod
    def from_env(cls) -> "PlatformProvisioner":
        return cls(
            guard=AuthorizationGuard(),
            watcher_spawner=PlatformWatcherSpawner(),
        )

    def provision(
        self,
        name: str,
        domain: str,
        regions: list[str],
        requested_by: str,
        run_context,
    ) -> dict:
        span = trace.get_current_span()
        channel = extract_channel(run_context)
        chat_id = extract_chat_id(run_context)

        user_id, err = self._guard.check(channel, chat_id, span)
        if err is not None:
            return err

        try:
            committer = GitOpsCommitter.from_env()
            yaml_content = yaml.safe_dump(
                PlatformManifest.build(
                    name=name, domain=domain, regions=regions
                ).model_dump(),
                default_flow_style=False,
                sort_keys=False,
            )
            safe_requested_by = requested_by.replace("\n", " ").replace("\r", " ")
            err = committer.commit(
                file_path=f"infrastructure/tenants/{name}.yaml",
                yaml_content=yaml_content,
                commit_message=(
                    f"feat(tenants): provision {name}\n\nRequested by: {safe_requested_by}"
                ),
            )
            if err is not None:
                log.info(
                    "Tenant %s already provisioning (manifest exists)",
                    name,
                    extra={"platform": name},
                )
                telemetry.provisioning_counter.add(1, {"outcome": "already_provisioning"})
                return err

            span.set_attribute("platform.name", name)
            telemetry.provisioning_counter.add(1, {"outcome": "started"})

            spawned = self._watcher_spawner.spawn(
                name=name,
                chat_id=chat_id,
                channel=channel,
                parent_span_ctx=span.get_span_context(),
            )
            if spawned:
                span.set_attribute("watcher.spawned", True)
                log.info("Watcher spawned for %s", name, extra={"platform": name})

            return {
                "status": "provisioning",
                "message": (
                    f"Request accepted. Tenant '{name}' provisioning has started."
                    " You will be notified when the status changes."
                ),
            }
        except Exception:
            log.exception("provision_platform_instance failed", extra={"platform": name})
            telemetry.provisioning_counter.add(1, {"outcome": "error"})
            return {
                "status": "error",
                "message": "Provisioning failed. Please try again later.",
            }


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

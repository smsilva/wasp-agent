import logging

import yaml
from opentelemetry import trace

import wasp.telemetry as telemetry
from wasp.auth_guard import AuthorizationGuard
from wasp.gitops_committer import GitOpsCommitter
from wasp.resources.platform.manifest import PlatformManifest
from wasp.watcher import PlatformWatcherSpawner, extract_channel, extract_chat_id

log = logging.getLogger(__name__)

DEFAULT_DOMAIN = "wasp.silvios.me"
DEFAULT_REGIONS = ("us-east-1",)


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

        if not requested_by:
            requested_by = user_id or "unknown"

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
                telemetry.provisioning_counter.add(
                    1, {"outcome": "already_provisioning"}
                )
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
            log.exception(
                "provision_platform_instance failed", extra={"platform": name}
            )
            telemetry.provisioning_counter.add(1, {"outcome": "error"})
            return {
                "status": "error",
                "message": "Provisioning failed. Please try again later.",
            }

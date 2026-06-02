import logging

import yaml
from opentelemetry import trace

import wasp.telemetry as telemetry
from wasp.auth_guard import AuthorizationGuard
from wasp.gitops_committer import GitOpsCommitter
from wasp.resources.cluster.manifest import ClusterManifest
from wasp.watcher import ClusterWatcherSpawner, extract_channel, extract_chat_id

log = logging.getLogger(__name__)


class ClusterProvisioner:
    def __init__(
        self,
        guard: AuthorizationGuard,
        watcher_spawner: ClusterWatcherSpawner,
    ):
        self._guard = guard
        self._watcher_spawner = watcher_spawner

    @classmethod
    def from_env(cls) -> "ClusterProvisioner":
        return cls(
            guard=AuthorizationGuard(),
            watcher_spawner=ClusterWatcherSpawner(),
        )

    def provision(
        self,
        name: str,
        kubernetes_version: str,
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
                ClusterManifest.build(
                    name=name, kubernetes_version=kubernetes_version
                ).model_dump(),
                default_flow_style=False,
                sort_keys=False,
            )
            safe_requested_by = requested_by.replace("\n", " ").replace("\r", " ")
            err = committer.commit(
                file_path=f"infrastructure/clusters/{name}.yaml",
                yaml_content=yaml_content,
                commit_message=(
                    f"feat(clusters): provision {name}\n\nRequested by: {safe_requested_by}"
                ),
            )
            if err is not None:
                log.info(
                    "Cluster %s already provisioning (manifest exists)",
                    name,
                    extra={"cluster": name},
                )
                telemetry.provisioning_counter.add(
                    1, {"outcome": "already_provisioning"}
                )
                return {
                    "status": "already_provisioning",
                    "message": f"Cluster '{name}' is already being provisioned.",
                }

            span.set_attribute("cluster.name", name)
            telemetry.provisioning_counter.add(1, {"outcome": "started"})

            spawned = self._watcher_spawner.spawn(
                name=name,
                chat_id=chat_id,
                channel=channel,
                parent_span_ctx=span.get_span_context(),
            )
            if spawned:
                span.set_attribute("watcher.spawned", True)
                log.info("Watcher spawned for %s", name, extra={"cluster": name})

            return {
                "status": "provisioning",
                "message": (
                    f"Request accepted. Cluster '{name}' provisioning has started."
                    " You will be notified when the status changes."
                ),
            }
        except Exception:
            log.exception("provision_cluster_instance failed", extra={"cluster": name})
            telemetry.provisioning_counter.add(1, {"outcome": "error"})
            return {
                "status": "error",
                "message": "Provisioning failed. Please try again later.",
            }

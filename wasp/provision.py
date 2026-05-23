import asyncio
import logging
import os
import threading

import wasp.telemetry as telemetry
import yaml
from agno.tools import tool
from opentelemetry import trace
from pydantic import BaseModel, Field
from wasp import auth
from wasp.git_client import FileAlreadyExistsError, PyGithubClient
from wasp.logging import chat_id_var
from wasp.notifier import ConsoleNotifier, Notifier, TelegramNotifier
from wasp.watcher import extract_channel, extract_chat_id, watch_platform

log = logging.getLogger(__name__)

TRUSTED_CHANNELS = {"local"}


def _select_notifier(channel: str | None = None) -> Notifier | None:
    kind = os.getenv("WASP_AGENT_NOTIFIER")
    token = os.getenv("TELEGRAM_TOKEN")
    if kind is None:
        if channel == "local":
            kind = "console"
        elif channel == "tg":
            kind = "telegram"
        else:
            kind = "telegram" if token else "console"
    if kind == "console":
        return ConsoleNotifier()
    if kind == "telegram":
        return TelegramNotifier(token=token) if token else None
    return None


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

    Returns: commit_sha, file_path, status.
    """
    if regions is None:
        regions = list(DEFAULT_REGIONS)

    channel = extract_channel(run_context)
    chat_id = extract_chat_id(run_context)

    user_id: str | None = None
    if channel and channel not in TRUSTED_CHANNELS:
        user_id = auth.is_authorized(channel, chat_id) if chat_id else None
        if user_id is None:
            log.warning(
                "auth denied: channel=%s channel_id=%s", channel, chat_id
            )
            telemetry.auth_denied(channel=channel, reason="unknown_identity")
            return {"status": "unauthorized", "message": "Acesso negado."}
    elif channel in TRUSTED_CHANNELS:
        user_id = "local-operator"

    current_span = trace.get_current_span()
    if user_id:
        current_span.set_attribute("user.id", user_id)
    if channel:
        current_span.set_attribute("auth.channel", channel)

    try:
        pat = os.getenv("GH_PAT")
        if not pat:
            raise ValueError("GH_PAT not set")

        manifest = PlatformManifest.build(name=name, domain=domain, regions=regions)
        yaml_content = yaml.safe_dump(
            manifest.model_dump(), default_flow_style=False, sort_keys=False
        )

        github_base_url = os.getenv("GITHUB_BASE_URL", "https://api.github.com")
        gitops_repo = os.getenv("GITOPS_REPO", "smsilva/wasp-gitops")
        client = PyGithubClient(pat=pat, repo=gitops_repo, base_url=github_base_url)
        file_path = f"infrastructure/tenants/{name}.yaml"
        safe_requested_by = requested_by.replace("\n", " ").replace("\r", " ")
        commit_message = (
            f"feat(tenants): provision {name}\n\nRequested by: {safe_requested_by}"
        )

        try:
            client.create_file(
                path=file_path,
                message=commit_message,
                content=yaml_content,
                branch="dev",
            )
        except FileAlreadyExistsError:
            log.info("Tenant %s already provisioning (manifest exists)", name, extra={"platform": name})
            telemetry.provisioning_counter.add(1, {"outcome": "already_provisioning"})
            return {
                "status": "already_provisioning",
                "message": f"Tenant '{name}' is already being provisioned.",
            }

        current_span.set_attribute("platform.name", name)

        telemetry.provisioning_counter.add(1, {"outcome": "started"})

        if chat_id:
            chat_id_var.set(chat_id)
        notifier = _select_notifier(channel)
        if chat_id and notifier is not None:
            current_span.set_attribute("watcher.spawned", True)
            parent_span_ctx = current_span.get_span_context()

            def _run_watcher():
                asyncio.run(watch_platform(name, chat_id, notifier, parent_span_ctx))

            threading.Thread(target=_run_watcher, daemon=True).start()
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

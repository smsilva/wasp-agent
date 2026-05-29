import asyncio
import logging
import os
import threading
import time

import wasp.telemetry as telemetry
from kubernetes.client import ApiException
from opentelemetry.trace import Link
from wasp.logging import chat_id_var
from wasp.clients import Notifier
from wasp.clients.k8s import load_kube_config_auto
from wasp.clients.local import ConsoleNotifier
from wasp.resources.platform import PLATFORM_GROUP, PLATFORM_PLURAL, PLATFORM_VERSION

log = logging.getLogger(__name__)


def _select_notifier(channel: str | None = None) -> Notifier | None:
    kind = os.getenv("WASP_AGENT_NOTIFIER")
    token = os.getenv("TELEGRAM_TOKEN")
    if kind is None:
        if channel == "local":
            kind = "console"
        elif channel == "tg":
            kind = "telegram"
        elif channel == "dc":
            kind = "discord"
        else:
            kind = "telegram" if token else "console"
    if kind == "console":
        return ConsoleNotifier()
    if kind == "telegram":
        from wasp.clients.telegram import TelegramNotifier

        return TelegramNotifier(token=token) if token else None
    if kind == "discord":
        import wasp.clients.discord as discord_pkg

        return discord_pkg._notifier
    return None


POLL_INTERVAL_SECONDS = 10
WATCH_TIMEOUT_SECONDS = 600


def extract_chat_id(run_context) -> str | None:
    if run_context is None:
        return None
    session_id = getattr(run_context, "session_id", None)
    if not session_id:
        return None
    parts = session_id.split(":")
    # agno session_id: <prefix>:<agent-name>:<chat_id>[:<message_short_id>]
    # prefix: "tg" (Telegram) | "local" (curl/CLI) | "dc" (Discord)
    if len(parts) >= 3 and parts[0] in ("tg", "local", "dc"):
        return parts[2]
    return None


def extract_channel(run_context) -> str | None:
    if run_context is None:
        return None
    session_id = getattr(run_context, "session_id", None)
    if not session_id:
        return None
    parts = session_id.split(":")
    if len(parts) >= 3 and parts[0] in ("tg", "local", "dc"):
        return parts[0]
    return None


def _find_condition(platform: dict, type_: str) -> dict | None:
    for c in platform.get("status", {}).get("conditions", []):
        if c.get("type") == type_:
            return c
    return None


async def watch_platform(
    name: str, chat_id: str, notifier: Notifier, parent_span_ctx=None
) -> None:
    chat_id_var.set(chat_id)
    log.info("Watcher started for %s", name, extra={"platform": name})
    try:
        await _watch_platform_inner(name, chat_id, notifier, parent_span_ctx)
    except Exception:
        log.exception("Watcher failed for %s", name, extra={"platform": name})


async def _watch_platform_inner(
    name: str, chat_id: str, notifier: Notifier, parent_span_ctx=None
) -> None:
    links = []
    if parent_span_ctx and parent_span_ctx.is_valid:
        links = [Link(parent_span_ctx)]

    with telemetry.tracer.start_as_current_span(
        "agent.watcher.lifecycle", links=links
    ) as span:
        span.set_attribute("platform.name", name)
        api = load_kube_config_auto()
        deadline = time.monotonic() + WATCH_TIMEOUT_SECONDS
        t0 = time.perf_counter()
        poll_count = 0

        while time.monotonic() < deadline:
            try:
                platform = api.get_cluster_custom_object(
                    group=PLATFORM_GROUP,
                    version=PLATFORM_VERSION,
                    plural=PLATFORM_PLURAL,
                    name=name,
                )
            except ApiException as e:
                if e.status == 404:
                    poll_count += 1
                    telemetry.watcher_polls_counter.add(1, {"result": "not_found"})
                    log.debug(
                        "Platform %s not in cluster yet, sleeping %ss",
                        name,
                        POLL_INTERVAL_SECONDS,
                    )
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue
                raise

            poll_count += 1
            condition = _find_condition(platform, "Ready")
            if condition and condition.get("status") == "True":
                telemetry.watcher_polls_counter.add(1, {"result": "ready"})
                elapsed = time.perf_counter() - t0
                telemetry.watcher_duration.record(elapsed, {"outcome": "ready"})
                span.set_attribute("outcome", "ready")
                span.set_attribute("poll_count", poll_count)
                span.set_attribute("duration_seconds", elapsed)
                log.info(
                    "Platform %s is Ready — notifying", name, extra={"platform": name}
                )
                await notifier.send(chat_id, ready_message(name, platform))
                return

            telemetry.watcher_polls_counter.add(1, {"result": "pending"})
            log.debug(
                "Platform %s not ready yet, sleeping %ss", name, POLL_INTERVAL_SECONDS
            )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        elapsed = time.perf_counter() - t0
        telemetry.watcher_duration.record(elapsed, {"outcome": "timeout"})
        span.set_attribute("outcome", "timeout")
        span.set_attribute("poll_count", poll_count)
        span.set_attribute("duration_seconds", elapsed)
        log.warning("Watcher timeout for %s", name, extra={"platform": name})
        await notifier.send(
            chat_id,
            f"Provisionamento de '{name}' ainda em andamento após 10 minutos. Verifique mais tarde.",
        )


def ready_message(name: str, platform: dict) -> str:
    spec = platform.get("spec", {})
    regions = spec.get("regions", [])
    lines = [f"Plataforma '{name}' está pronta."]
    for r in regions:
        endpoint = r.get("endpoint")
        if endpoint:
            lines.append(f"- {r['name']}: https://{endpoint}")
    return "\n".join(lines)


class PlatformWatcherSpawner:
    def spawn(
        self,
        name: str,
        chat_id: str | None,
        channel: str | None,
        parent_span_ctx,
    ) -> bool:
        if not chat_id:
            return False
        chat_id_var.set(chat_id)
        notifier = _select_notifier(channel)
        if notifier is None:
            return False

        def _run_watcher():
            asyncio.run(watch_platform(name, chat_id, notifier, parent_span_ctx))

        threading.Thread(target=_run_watcher, daemon=True).start()
        return True

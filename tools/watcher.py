import asyncio
import time

import httpx
from kubernetes import client, config
from kubernetes.client import ApiException

PLATFORM_GROUP = "wasp.silvios.me"
PLATFORM_VERSION = "v1alpha1"
PLATFORM_PLURAL = "platforms"
POLL_INTERVAL_SECONDS = 10
WATCH_TIMEOUT_SECONDS = 600
TELEGRAM_API_BASE = "https://api.telegram.org"


def load_kube_config_auto() -> "client.CustomObjectsApi":
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CustomObjectsApi()


def extract_chat_id(run_context) -> str | None:
    if run_context is None:
        return None
    session_id = getattr(run_context, "session_id", None)
    if not session_id:
        return None
    parts = session_id.split(":")
    if len(parts) >= 3 and parts[0] == "tg":
        return parts[-1]
    return None


def _find_condition(platform: dict, type_: str) -> dict | None:
    for c in platform.get("status", {}).get("conditions", []):
        if c.get("type") == type_:
            return c
    return None


async def notify_telegram(chat_id: str, token: str, text: str) -> None:
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as http:
        await http.post(url, json={"chat_id": chat_id, "text": text})


async def watch_platform(name: str, chat_id: str, token: str) -> None:
    api = load_kube_config_auto()
    deadline = time.monotonic() + WATCH_TIMEOUT_SECONDS

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
                await notify_telegram(chat_id, token, f"Platform '{name}' não encontrada no cluster.")
                return
            raise

        condition = _find_condition(platform, "Ready")
        if condition and condition.get("status") == "True":
            await notify_telegram(chat_id, token, ready_message(name, platform))
            return

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    await notify_telegram(
        chat_id,
        token,
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

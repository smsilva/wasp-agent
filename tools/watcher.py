from kubernetes import client, config


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


def ready_message(name: str, platform: dict) -> str:
    spec = platform.get("spec", {})
    regions = spec.get("regions", [])
    lines = [f"Plataforma '{name}' está pronta."]
    for r in regions:
        endpoint = r.get("endpoint")
        if endpoint:
            lines.append(f"- {r['name']}: https://{endpoint}")
    return "\n".join(lines)

import os
import subprocess
import threading
import time

import httpx
import pytest

import json

GITEA_PORT = 3456
GITEA_CONTAINER = "wasp-e2e-gitea"
GITEA_ADMIN = "root"


def sse_content(response) -> str:
    """Extract content from the RunCompleted event in an SSE response."""
    for block in response.text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        event = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if event == "RunCompleted" and data:
            return json.loads(data).get("content", "") or ""
    return ""


def sse_events(response) -> list[dict]:
    """Return all SSE events as a list of {event, data} dicts — useful for debugging."""
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        event = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if event:
            events.append({"event": event, "data": json.loads(data) if data else None})
    return events


GITEA_PASS = "password123"  # noqa: S105 — test credential only


# ─── helpers ──────────────────────────────────────────────────────────────────


class GiteaClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self._headers = {"Authorization": f"token {token}"}

    def get_latest_commit(self, repo: str) -> str:
        r = httpx.get(
            f"{self.base_url}/api/v1/repos/{GITEA_ADMIN}/{repo}/commits?limit=1",
            headers=self._headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()[0]["sha"]

    def get_file(self, sha: str, path: str, repo: str = "wasp-gitops") -> str:
        r = httpx.get(
            f"{self.base_url}/api/v1/repos/{GITEA_ADMIN}/{repo}/raw/{path}?ref={sha}",
            headers=self._headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.text


# ─── k3d cluster ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def k3d_cluster():
    # Use K3D_CLUSTER if set (external cluster — not created/deleted by tests).
    # In CI, leave it unset so the fixture creates an ephemeral cluster.
    external = os.environ.get("K3D_CLUSTER")
    cluster_name = external or "wasp-e2e"

    if not external:
        subprocess.run(["k3d", "cluster", "delete", cluster_name], check=False)
        subprocess.run(
            ["k3d", "cluster", "create", cluster_name],
            check=True,
        )
        subprocess.run(
            [
                "kubectl",
                "wait",
                "--context",
                f"k3d-{cluster_name}",
                "--for=condition=Ready",
                "node",
                "--all",
                "--timeout=120s",
            ],
            check=True,
        )

    subprocess.run(
        [
            "kubectl",
            "apply",
            "--context",
            f"k3d-{cluster_name}",
            "--validate=false",
            "-f",
            "tests/e2e/fixtures/platform-crd.yaml",
        ],
        check=True,
    )
    yield cluster_name

    if not external:
        subprocess.run(["k3d", "cluster", "delete", cluster_name], check=True)


# ─── Gitea container ──────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def gitea_container():
    subprocess.run(["docker", "rm", "--force", GITEA_CONTAINER], check=False)
    subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            GITEA_CONTAINER,
            "-p",
            f"{GITEA_PORT}:3000",
            "-e",
            "GITEA__security__INSTALL_LOCK=true",
            "-e",
            "GITEA__server__OFFLINE_MODE=true",
            "gitea/gitea:1.22",
        ],
        check=True,
    )

    base_url = f"http://localhost:{GITEA_PORT}"

    for _ in range(30):
        try:
            r = httpx.get(f"{base_url}/api/v1/version", timeout=3)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        subprocess.run(["docker", "rm", "-f", GITEA_CONTAINER])
        raise RuntimeError("Gitea did not start within 60s")

    subprocess.run(
        [
            "docker",
            "exec",
            "--user",
            "git",
            GITEA_CONTAINER,
            "gitea",
            "admin",
            "user",
            "create",
            "--username",
            GITEA_ADMIN,
            "--password",
            GITEA_PASS,
            "--email",
            "root@localhost",
            "--admin",
            "--must-change-password=false",
        ],
        check=True,
    )

    r = httpx.post(
        f"{base_url}/api/v1/users/{GITEA_ADMIN}/tokens",
        auth=(GITEA_ADMIN, GITEA_PASS),
        json={
            "name": "e2e-token",
            "scopes": ["write:repository", "read:user", "write:user"],
        },
        timeout=10,
    )
    r.raise_for_status()
    token = r.json()["sha1"]

    httpx.post(
        f"{base_url}/api/v1/user/repos",
        headers={"Authorization": f"token {token}"},
        json={"name": "wasp-gitops", "auto_init": True, "default_branch": "dev"},
        timeout=10,
    ).raise_for_status()

    yield GiteaClient(base_url=base_url, token=token)

    subprocess.run(["docker", "rm", "-f", GITEA_CONTAINER], check=True)


# ─── recording notifier ───────────────────────────────────────────────────────


@pytest.fixture
def recording_notifier():
    from wasp.notifier import RecordingNotifier

    return RecordingNotifier()


# ─── agent client ─────────────────────────────────────────────────────────────


@pytest.fixture
async def agent_client(gitea_container, recording_notifier, monkeypatch):
    monkeypatch.setenv("GH_PAT", gitea_container.token)
    monkeypatch.setenv("GITHUB_BASE_URL", f"{gitea_container.base_url}/api/v1")
    monkeypatch.setenv("GITOPS_REPO", f"{GITEA_ADMIN}/wasp-gitops")
    monkeypatch.setenv(
        "TELEGRAM_TOKEN", "123456789:AAHfiqksKZ8WmR2zggAY0gUMQyxFAq0k8I0"
    )
    monkeypatch.setenv("PROMETHEUS_METRICS_ACTIVE", "true")

    import wasp.provision
    import wasp.auth
    import main  # noqa: F401
    import wasp.telemetry as _telemetry

    _telemetry.configure()  # force reconfigure now that PROMETHEUS_PORT is set
    from wasp.git_client import GiteaClient

    monkeypatch.setattr(
        wasp.provision, "_select_notifier", lambda *a, **kw: recording_notifier
    )
    monkeypatch.setattr(
        wasp.auth, "is_authorized", lambda channel, channel_id: "e2e-user"
    )
    monkeypatch.setattr(
        wasp.provision,
        "PyGithubClient",
        lambda **_kw: GiteaClient(
            token=gitea_container.token,
            repo=f"{GITEA_ADMIN}/wasp-gitops",
            base_url=gitea_container.base_url,
        ),
    )

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", timeout=60
    ) as c:
        yield c


# ─── fake reconciler ──────────────────────────────────────────────────────────


@pytest.fixture
def fake_reconciler(k3d_cluster):
    from kubernetes import client as k8s_client, config as k8s_config

    stop = threading.Event()

    def _run():
        k8s_config.load_kube_config(context=f"k3d-{k3d_cluster}")
        api = k8s_client.CustomObjectsApi()
        while not stop.is_set():
            try:
                platforms = api.list_cluster_custom_object(
                    group="wasp.silvios.me",
                    version="v1alpha1",
                    plural="platforms",
                )
                for p in platforms.get("items", []):
                    name = p["metadata"]["name"]
                    conditions = p.get("status", {}).get("conditions", [])
                    if any(
                        c.get("type") == "Ready" and c.get("status") == "True"
                        for c in conditions
                    ):
                        continue
                    time.sleep(3)
                    api.patch_cluster_custom_object_status(
                        group="wasp.silvios.me",
                        version="v1alpha1",
                        plural="platforms",
                        name=name,
                        body={
                            "status": {
                                "conditions": [
                                    {
                                        "type": "Ready",
                                        "status": "True",
                                        "reason": "Available",
                                    }
                                ]
                            }
                        },
                    )
            except Exception:
                pass
            time.sleep(1)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    yield
    stop.set()
    t.join(timeout=10)

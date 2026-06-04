"""
E2E test: full provisioning flow.

Requires: k3d, docker, ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN (llmproxy).
Run with: pytest -m e2e --no-cov
"""

import asyncio
import subprocess
import uuid

import pytest

from tests.e2e.conftest import sse_content


PLATFORM_NAME = "wp-test"


@pytest.mark.e2e
async def test_provision_and_notify(
    agent_client,
    gitea_container,
    k3d_cluster,
    fake_reconciler,
    recording_notifier,
):
    session = f"tg:wasp-agent:{uuid.uuid4().hex[:8]}"
    # turn 1 — agent must ask for confirmation before provisioning
    r1 = await agent_client.post(
        "/agents/wasp-agent/runs",
        data={"message": f"Cria platform {PLATFORM_NAME}", "session_id": session},
    )
    assert r1.status_code == 200, r1.text
    content1 = sse_content(r1)
    # "confirm" cobre EN ("Confirm...") e PT ("Confirma..."); o modelo varia o idioma
    assert "confirm" in content1.lower(), (
        f"Expected confirmation, got: {content1!r}\nFull SSE response:\n{r1.text}"
    )

    # turn 2 — user confirms; agent calls provision_platform_instance
    r2 = await agent_client.post(
        "/agents/wasp-agent/runs",
        data={"message": "sim", "session_id": session},
    )
    assert r2.status_code == 200, r2.text

    # validate git push to Gitea
    commit = gitea_container.get_latest_commit("wasp-gitops")
    yaml_content = gitea_container.get_file(
        commit, f"infrastructure/tenants/{PLATFORM_NAME}.yaml"
    )
    assert PLATFORM_NAME in yaml_content

    # apply Platform CR to k3d (simulating ArgoCD sync)
    subprocess.run(
        ["kubectl", "apply", "--context", f"k3d-{k3d_cluster}", "-f", "-"],
        input=yaml_content,
        capture_output=True,
        text=True,
        check=True,
    )

    # wait for watcher to receive the Ready notification (fake_reconciler sets it after 3s)
    await asyncio.wait_for(recording_notifier.wait_for_message(), timeout=60)
    assert any(PLATFORM_NAME in m["text"] for m in recording_notifier.messages)

    # validate Prometheus metric incremented
    r = await agent_client.get("/telemetry/prometheus")
    assert r.status_code == 200
    assert "agent_provisioning_total" in r.text

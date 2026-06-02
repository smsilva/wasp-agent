# CRD Cluster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar o recurso `Cluster` (manifest, provisioner, inventory, provider, watcher) seguindo o padrão de `Platform`, sem editar `agent.py`.

**Architecture:** O agente commita um manifesto `Cluster` em `infrastructure/clusters/{name}.yaml` no repo GitOps; o Crossplane reconcilia via Composition. Cada CRD expõe um `ResourceProvider` registrado em `PROVIDERS`; o watcher monitora a condição `Ready` e notifica. Sem abstração genérica de watcher (2 CRDs não justificam).

**Tech Stack:** Python, Pydantic, agno `@tool`, kubernetes `CustomObjectsApi`, OpenTelemetry, pytest.

---

## Notes for the implementer

- Read these existing files first to internalize the pattern — the Cluster code mirrors them almost exactly:
  - `wasp/resources/platform/{manifest,provisioner,inventory,provider}.py`
  - `wasp/resources/platform/__init__.py`
  - `wasp/watcher.py` (the `watch_platform` / `PlatformWatcherSpawner` section)
  - `wasp/provision.py`
- `make test` requires Docker (Postgres testcontainers). Run individual tests with `pytest tests/<file>::<test> -v` during the loop.
- Coverage must stay at 100% (`pytest --cov`). The final task verifies this.
- After ANY change touching `wasp/`, the `mock_agno` fixture in `tests/conftest.py` must list the new modules (Task 7) — otherwise state leaks between tests. Do Task 7 before relying on full-suite runs.
- `GitOpsCommitter.commit` hardcodes the `already_provisioning` message with the word "Tenant". The Cluster provisioner rewrites that message to say "Cluster" (Task 2, Step 3).

---

## Task 1: Cluster manifest

**Files:**
- Create: `wasp/resources/cluster/__init__.py`
- Create: `wasp/resources/cluster/manifest.py`
- Test: `tests/test_cluster_manifest.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cluster_manifest.py`:

```python
def test_manifest_build_defaults():
    from wasp.resources.cluster import ClusterManifest

    manifest = ClusterManifest.build(name="edge")

    assert manifest.metadata.name == "edge"
    assert manifest.kind == "Cluster"
    assert manifest.apiVersion == "wasp.silvios.me/v1alpha1"
    assert manifest.spec.kubernetesVersion == "1.34"


def test_manifest_build_explicit_version():
    from wasp.resources.cluster import ClusterManifest

    manifest = ClusterManifest.build(name="edge", kubernetes_version="1.33")

    assert manifest.spec.kubernetesVersion == "1.33"


def test_manifest_yaml_output():
    import yaml
    from wasp.resources.cluster import ClusterManifest

    manifest = ClusterManifest.build("edge")
    yaml_str = yaml.dump(
        manifest.model_dump(), default_flow_style=False, sort_keys=False
    )
    data = yaml.safe_load(yaml_str)

    assert data["apiVersion"] == "wasp.silvios.me/v1alpha1"
    assert data["kind"] == "Cluster"
    assert data["metadata"]["name"] == "edge"
    assert data["spec"]["kubernetesVersion"] == "1.34"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cluster_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wasp.resources.cluster'`

- [ ] **Step 3: Create the manifest**

Create `wasp/resources/cluster/manifest.py`:

```python
from pydantic import BaseModel

from wasp.resources.base import MetadataSpec, ResourceManifest

CLUSTER_GROUP = "wasp.silvios.me"
CLUSTER_VERSION = "v1alpha1"
CLUSTER_PLURAL = "clusters"

DEFAULT_KUBERNETES_VERSION = "1.34"


class ClusterSpec(BaseModel):
    kubernetesVersion: str = DEFAULT_KUBERNETES_VERSION


class ClusterManifest(ResourceManifest):
    kind: str = "Cluster"
    spec: ClusterSpec

    @classmethod
    def build(
        cls, name: str, kubernetes_version: str = DEFAULT_KUBERNETES_VERSION
    ) -> "ClusterManifest":
        return cls(
            metadata=MetadataSpec(name=name),
            spec=ClusterSpec(kubernetesVersion=kubernetes_version),
        )
```

Create `wasp/resources/cluster/__init__.py` (manifest re-exports only for now; provisioner/inventory added in later tasks):

```python
from wasp.resources.cluster.manifest import (
    CLUSTER_GROUP as CLUSTER_GROUP,
)
from wasp.resources.cluster.manifest import (
    CLUSTER_PLURAL as CLUSTER_PLURAL,
)
from wasp.resources.cluster.manifest import (
    CLUSTER_VERSION as CLUSTER_VERSION,
)
from wasp.resources.cluster.manifest import (
    DEFAULT_KUBERNETES_VERSION as DEFAULT_KUBERNETES_VERSION,
)
from wasp.resources.cluster.manifest import (
    ClusterManifest as ClusterManifest,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cluster_manifest.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add wasp/resources/cluster/__init__.py wasp/resources/cluster/manifest.py tests/test_cluster_manifest.py
git commit -m "feat(cluster): add Cluster manifest"
```

---

## Task 2: Cluster provisioner

**Files:**
- Create: `wasp/resources/cluster/provisioner.py`
- Modify: `wasp/resources/cluster/__init__.py`
- Test: covered via `tests/test_provision.py` in Task 5 (the provisioner is exercised through the `@tool` wrapper). This task only adds the class + a focused unit test for the message rewrite.
- Test: `tests/test_cluster_provisioner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cluster_provisioner.py`:

```python
from unittest.mock import MagicMock


def test_provisioner_commits_to_clusters_path(monkeypatch):
    from wasp.resources.cluster.provisioner import ClusterProvisioner

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setenv("GITHUB_BASE_URL", "https://api.github.com")
    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)
    spawner = MagicMock()
    spawner.spawn.return_value = False

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterProvisioner(guard=guard, watcher_spawner=spawner).provision(
        name="edge",
        kubernetes_version="1.34",
        requested_by="alice",
        run_context=FakeCtx(),
    )

    call_kwargs = mock_client.create_file.call_args.kwargs
    assert call_kwargs["path"] == "infrastructure/clusters/edge.yaml"
    assert "feat(clusters): provision edge" in call_kwargs["message"]
    assert "Requested by: alice" in call_kwargs["message"]
    assert result["status"] == "provisioning"
    assert "edge" in result["message"]


def test_provisioner_rewrites_already_provisioning_message(monkeypatch):
    from wasp.git_client import FileAlreadyExistsError
    from wasp.resources.cluster.provisioner import ClusterProvisioner

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setenv("GITHUB_BASE_URL", "https://api.github.com")
    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value
    mock_client.create_file.side_effect = FileAlreadyExistsError(
        "infrastructure/clusters/edge.yaml"
    )
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)
    spawner = MagicMock()

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterProvisioner(guard=guard, watcher_spawner=spawner).provision(
        name="edge",
        kubernetes_version="1.34",
        requested_by="alice",
        run_context=FakeCtx(),
    )

    assert result["status"] == "already_provisioning"
    assert "Cluster 'edge'" in result["message"]
    spawner.spawn.assert_not_called()


def test_provisioner_returns_unauthorized_when_guard_denies():
    from wasp.resources.cluster.provisioner import ClusterProvisioner

    guard = MagicMock()
    guard.check.return_value = (
        None,
        {"status": "unauthorized", "message": "Acesso negado."},
    )
    spawner = MagicMock()

    class FakeCtx:
        session_id = "tg:wasp-agent:999"

    result = ClusterProvisioner(guard=guard, watcher_spawner=spawner).provision(
        name="edge",
        kubernetes_version="1.34",
        requested_by="",
        run_context=FakeCtx(),
    )

    assert result == {"status": "unauthorized", "message": "Acesso negado."}


def test_provisioner_returns_error_on_exception(monkeypatch):
    from wasp.resources.cluster.provisioner import ClusterProvisioner

    monkeypatch.delenv("GH_PAT", raising=False)
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)
    spawner = MagicMock()

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterProvisioner(guard=guard, watcher_spawner=spawner).provision(
        name="edge",
        kubernetes_version="1.34",
        requested_by="",
        run_context=FakeCtx(),
    )

    assert result["status"] == "error"
    assert result["message"] == "Provisioning failed. Please try again later."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cluster_provisioner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wasp.resources.cluster.provisioner'`

- [ ] **Step 3: Create the provisioner**

Create `wasp/resources/cluster/provisioner.py`:

```python
import logging

import yaml
from opentelemetry import trace

import wasp.telemetry as telemetry
from wasp.auth_guard import AuthorizationGuard
from wasp.gitops_committer import GitOpsCommitter
from wasp.resources.cluster.manifest import (
    DEFAULT_KUBERNETES_VERSION,
    ClusterManifest,
)
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
            log.exception(
                "provision_cluster_instance failed", extra={"cluster": name}
            )
            telemetry.provisioning_counter.add(1, {"outcome": "error"})
            return {
                "status": "error",
                "message": "Provisioning failed. Please try again later.",
            }
```

> NOTE: `DEFAULT_KUBERNETES_VERSION` is imported here only to keep the import surface symmetric with `provision.py` (Task 5 imports it from the package `__init__`). It is not referenced inside the method body — the default lives in the `@tool` signature. If ruff flags it as unused (F401), remove this single import line; the package re-export in Step 4 is what `provision.py` actually consumes.

Update `wasp/resources/cluster/__init__.py` — append:

```python
from wasp.resources.cluster.provisioner import (
    ClusterProvisioner as ClusterProvisioner,
)
```

- [ ] **Step 4: Run tests to verify they pass** (and depends on Task 3's `ClusterWatcherSpawner`)

> DEPENDENCY: `wasp/resources/cluster/provisioner.py` imports `ClusterWatcherSpawner` from `wasp.watcher`, which is created in Task 3. If you are executing strictly in order, do Task 3 BEFORE running this step. The TDD ordering here is intentional: write provisioner tests first (Step 1-2), then implement the watcher (Task 3), then implement the provisioner (Step 3), then run.

Run: `pytest tests/test_cluster_provisioner.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add wasp/resources/cluster/provisioner.py wasp/resources/cluster/__init__.py tests/test_cluster_provisioner.py
git commit -m "feat(cluster): add Cluster provisioner"
```

---

## Task 3: Cluster watcher

**Files:**
- Modify: `wasp/watcher.py` (add `watch_cluster`, `_watch_cluster_inner`, `cluster_ready_message`, `ClusterWatcherSpawner` after the existing Platform watcher code)
- Test: `tests/test_cluster_watcher.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cluster_watcher.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock


def test_cluster_ready_message_includes_version():
    from wasp.watcher import cluster_ready_message

    cluster = {"spec": {"kubernetesVersion": "1.34"}}
    msg = cluster_ready_message("edge", cluster)

    assert "edge" in msg
    assert "1.34" in msg


def test_watch_cluster_notifies_when_ready(monkeypatch):
    from wasp import watcher

    mock_api = MagicMock()
    mock_api.get_cluster_custom_object.return_value = {
        "spec": {"kubernetesVersion": "1.34"},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(watcher, "load_kube_config_auto", lambda: mock_api)

    notifier = MagicMock()
    notifier.send = AsyncMock()

    asyncio.run(watcher.watch_cluster("edge", "chat-1", notifier))

    notifier.send.assert_awaited_once()
    sent = notifier.send.await_args.args[1]
    assert "edge" in sent
    assert "1.34" in sent


def test_cluster_watcher_spawner_skips_without_chat_id():
    from wasp.watcher import ClusterWatcherSpawner

    spawned = ClusterWatcherSpawner().spawn(
        name="edge", chat_id=None, channel="tg", parent_span_ctx=None
    )

    assert spawned is False


def test_cluster_watcher_spawner_starts_thread(monkeypatch):
    from wasp import watcher
    from wasp.watcher import ClusterWatcherSpawner

    mock_thread = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread)
    monkeypatch.setattr(watcher.threading, "Thread", mock_thread_cls)
    monkeypatch.setattr(watcher, "_select_notifier", lambda channel: MagicMock())

    spawned = ClusterWatcherSpawner().spawn(
        name="edge", chat_id="chat-1", channel="local", parent_span_ctx=None
    )

    assert spawned is True
    mock_thread.start.assert_called_once()


def test_cluster_watcher_spawner_skips_without_notifier(monkeypatch):
    from wasp import watcher
    from wasp.watcher import ClusterWatcherSpawner

    monkeypatch.setattr(watcher, "_select_notifier", lambda channel: None)

    spawned = ClusterWatcherSpawner().spawn(
        name="edge", chat_id="chat-1", channel="tg", parent_span_ctx=None
    )

    assert spawned is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cluster_watcher.py -v`
Expected: FAIL with `ImportError: cannot import name 'cluster_ready_message'` (or `ClusterWatcherSpawner`)

- [ ] **Step 3: Implement the cluster watcher**

In `wasp/watcher.py`, add `CLUSTER_*` to the existing resource import line. Change:

```python
from wasp.resources.platform import PLATFORM_GROUP, PLATFORM_PLURAL, PLATFORM_VERSION
```

to:

```python
from wasp.resources.cluster import CLUSTER_GROUP, CLUSTER_PLURAL, CLUSTER_VERSION
from wasp.resources.platform import PLATFORM_GROUP, PLATFORM_PLURAL, PLATFORM_VERSION
```

Then append at the end of `wasp/watcher.py` (after `PlatformWatcherSpawner`):

```python
async def watch_cluster(
    name: str, chat_id: str, notifier: Notifier, parent_span_ctx=None
) -> None:
    chat_id_var.set(chat_id)
    log.info("Cluster watcher started for %s", name, extra={"cluster": name})
    try:
        await _watch_cluster_inner(name, chat_id, notifier, parent_span_ctx)
    except Exception:
        log.exception("Cluster watcher failed for %s", name, extra={"cluster": name})


async def _watch_cluster_inner(
    name: str, chat_id: str, notifier: Notifier, parent_span_ctx=None
) -> None:
    links = []
    if parent_span_ctx and parent_span_ctx.is_valid:
        links = [Link(parent_span_ctx)]

    with telemetry.tracer.start_as_current_span(
        "agent.watcher.lifecycle", links=links
    ) as span:
        span.set_attribute("cluster.name", name)
        api = load_kube_config_auto()
        deadline = time.monotonic() + WATCH_TIMEOUT_SECONDS
        t0 = time.perf_counter()
        poll_count = 0

        while time.monotonic() < deadline:
            try:
                cluster = api.get_cluster_custom_object(
                    group=CLUSTER_GROUP,
                    version=CLUSTER_VERSION,
                    plural=CLUSTER_PLURAL,
                    name=name,
                )
            except ApiException as e:
                if e.status == 404:
                    poll_count += 1
                    telemetry.watcher_polls_counter.add(1, {"result": "not_found"})
                    log.debug(
                        "Cluster %s not in cluster yet, sleeping %ss",
                        name,
                        POLL_INTERVAL_SECONDS,
                    )
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue
                raise

            poll_count += 1
            condition = _find_condition(cluster, "Ready")
            if condition and condition.get("status") == "True":
                telemetry.watcher_polls_counter.add(1, {"result": "ready"})
                elapsed = time.perf_counter() - t0
                telemetry.watcher_duration.record(elapsed, {"outcome": "ready"})
                span.set_attribute("outcome", "ready")
                span.set_attribute("poll_count", poll_count)
                span.set_attribute("duration_seconds", elapsed)
                log.info(
                    "Cluster %s is Ready — notifying", name, extra={"cluster": name}
                )
                await notifier.send(chat_id, cluster_ready_message(name, cluster))
                return

            telemetry.watcher_polls_counter.add(1, {"result": "pending"})
            log.debug(
                "Cluster %s not ready yet, sleeping %ss", name, POLL_INTERVAL_SECONDS
            )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        elapsed = time.perf_counter() - t0
        telemetry.watcher_duration.record(elapsed, {"outcome": "timeout"})
        span.set_attribute("outcome", "timeout")
        span.set_attribute("poll_count", poll_count)
        span.set_attribute("duration_seconds", elapsed)
        log.warning("Cluster watcher timeout for %s", name, extra={"cluster": name})
        await notifier.send(
            chat_id,
            f"Provisionamento do cluster '{name}' ainda em andamento após 10 minutos. Verifique mais tarde.",
        )


def cluster_ready_message(name: str, cluster: dict) -> str:
    version = cluster.get("spec", {}).get("kubernetesVersion", "")
    return f"Cluster '{name}' está pronto (Kubernetes {version})."


class ClusterWatcherSpawner:
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
            asyncio.run(watch_cluster(name, chat_id, notifier, parent_span_ctx))

        threading.Thread(target=_run_watcher, daemon=True).start()
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cluster_watcher.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add wasp/watcher.py tests/test_cluster_watcher.py
git commit -m "feat(cluster): add Cluster watcher"
```

---

## Task 4: Cluster inventory

**Files:**
- Create: `wasp/resources/cluster/inventory.py`
- Modify: `wasp/resources/cluster/__init__.py`
- Test: `tests/test_cluster_inventory.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cluster_inventory.py`:

```python
from unittest.mock import MagicMock


def test_status_from_conditions_ready():
    from wasp.resources.cluster.inventory import _status_from_conditions

    cluster = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
    assert _status_from_conditions(cluster) == "Ready"


def test_status_from_conditions_pending():
    from wasp.resources.cluster.inventory import _status_from_conditions

    cluster = {"status": {"conditions": [{"type": "Ready", "status": "False"}]}}
    assert _status_from_conditions(cluster) == "Pending"


def test_status_from_conditions_unknown_when_missing():
    from wasp.resources.cluster.inventory import _status_from_conditions

    assert _status_from_conditions({"status": {"conditions": []}}) == "Unknown"
    assert _status_from_conditions({}) == "Unknown"


def test_inventory_list_transforms_items():
    from wasp.resources.cluster.inventory import ClusterInventory

    reader = MagicMock()
    reader.search_for_instance_of.return_value = [
        {
            "metadata": {"name": "edge"},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        },
        {
            "metadata": {"name": "core"},
            "status": {"conditions": [{"type": "Ready", "status": "False"}]},
        },
        {"metadata": {"name": "fresh"}, "status": {}},
    ]
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterInventory(guard=guard, reader=reader).list(FakeCtx())

    assert result == {
        "status": "ok",
        "clusters": [
            {"name": "edge", "status": "Ready"},
            {"name": "core", "status": "Pending"},
            {"name": "fresh", "status": "Unknown"},
        ],
    }


def test_inventory_list_calls_reader_with_cluster_gvp():
    from wasp.resources.cluster.inventory import ClusterInventory
    from wasp.resources.cluster.manifest import (
        CLUSTER_GROUP,
        CLUSTER_PLURAL,
        CLUSTER_VERSION,
    )

    reader = MagicMock()
    reader.search_for_instance_of.return_value = []
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    ClusterInventory(guard=guard, reader=reader).list(FakeCtx())

    reader.search_for_instance_of.assert_called_once_with(
        CLUSTER_GROUP, CLUSTER_VERSION, CLUSTER_PLURAL
    )


def test_inventory_list_returns_unauthorized_when_guard_denies():
    from wasp.resources.cluster.inventory import ClusterInventory

    reader = MagicMock()
    guard = MagicMock()
    guard.check.return_value = (
        None,
        {"status": "unauthorized", "message": "Acesso negado."},
    )

    class FakeCtx:
        session_id = "tg:wasp-agent:999"

    result = ClusterInventory(guard=guard, reader=reader).list(FakeCtx())

    assert result == {"status": "unauthorized", "message": "Acesso negado."}
    reader.search_for_instance_of.assert_not_called()


def test_inventory_list_returns_error_on_exception():
    from wasp.resources.cluster.inventory import ClusterInventory

    reader = MagicMock()
    reader.search_for_instance_of.side_effect = RuntimeError("boom")
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterInventory(guard=guard, reader=reader).list(FakeCtx())

    assert result["status"] == "error"
    assert result["message"] == "List failed. Please try again later."


def test_inventory_get_returns_message_when_ready():
    from wasp.resources.cluster.inventory import ClusterInventory

    reader = MagicMock()
    reader.get_by_name.return_value = {
        "metadata": {"name": "edge"},
        "status": {
            "conditions": [
                {
                    "type": "Ready",
                    "status": "True",
                    "lastTransitionTime": "2026-05-30T10:00:00Z",
                }
            ]
        },
    }
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterInventory(guard=guard, reader=reader).get("edge", FakeCtx())

    assert result["status"] == "Ready"
    assert result["name"] == "edge"
    assert result["message"] == "O Cluster edge está Ready desde 30/05."


def test_inventory_get_returns_message_when_not_found():
    from wasp.resources.cluster.inventory import ClusterInventory

    reader = MagicMock()
    reader.get_by_name.return_value = None
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterInventory(guard=guard, reader=reader).get("ghost", FakeCtx())

    assert result["status"] == "not_found"
    assert result["name"] == "ghost"
    assert "ghost" in result["message"]


def test_inventory_get_returns_unauthorized_when_guard_denies():
    from wasp.resources.cluster.inventory import ClusterInventory

    reader = MagicMock()
    guard = MagicMock()
    guard.check.return_value = (
        None,
        {"status": "unauthorized", "message": "Acesso negado."},
    )

    class FakeCtx:
        session_id = "tg:wasp-agent:999"

    result = ClusterInventory(guard=guard, reader=reader).get("edge", FakeCtx())

    assert result == {"status": "unauthorized", "message": "Acesso negado."}
    reader.get_by_name.assert_not_called()


def test_inventory_get_returns_error_on_exception():
    from wasp.resources.cluster.inventory import ClusterInventory

    reader = MagicMock()
    reader.get_by_name.side_effect = RuntimeError("boom")
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterInventory(guard=guard, reader=reader).get("edge", FakeCtx())

    assert result["status"] == "error"


def test_format_transition_date_returns_none_for_invalid_timestamp():
    from wasp.resources.cluster.inventory import _format_transition_date

    assert _format_transition_date({"lastTransitionTime": "not-a-date"}) is None


def test_inventory_get_message_without_transition_time():
    from wasp.resources.cluster.inventory import ClusterInventory

    reader = MagicMock()
    reader.get_by_name.return_value = {
        "metadata": {"name": "edge"},
        "status": {"conditions": [{"type": "Ready", "status": "False"}]},
    }
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterInventory(guard=guard, reader=reader).get("edge", FakeCtx())

    assert result["status"] == "Pending"
    assert "edge" in result["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cluster_inventory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wasp.resources.cluster.inventory'`

- [ ] **Step 3: Create the inventory**

Create `wasp/resources/cluster/inventory.py`:

```python
import logging
from datetime import datetime

from opentelemetry import trace

from wasp.auth_guard import AuthorizationGuard
from wasp.clients.k8s import KubernetesResourceReader
from wasp.resources.cluster.manifest import (
    CLUSTER_GROUP,
    CLUSTER_PLURAL,
    CLUSTER_VERSION,
)
from wasp.watcher import extract_channel, extract_chat_id

log = logging.getLogger(__name__)


def _status_from_conditions(cluster: dict) -> str:
    for c in cluster.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return "Ready" if c.get("status") == "True" else "Pending"
    return "Unknown"


def _ready_condition(cluster: dict) -> dict | None:
    for c in cluster.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return c
    return None


def _format_transition_date(condition: dict | None) -> str | None:
    if condition is None:
        return None
    ts = condition.get("lastTransitionTime")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d/%m")
    except ValueError:
        return None


def _status_message(name: str, status: str, condition: dict | None) -> str:
    date = _format_transition_date(condition)
    if date:
        return f"O Cluster {name} está {status} desde {date}."
    return f"O Cluster {name} está {status}."


class ClusterInventory:
    def __init__(
        self,
        guard: AuthorizationGuard,
        reader: KubernetesResourceReader,
    ):
        self._guard = guard
        self._reader = reader

    @classmethod
    def from_env(cls) -> "ClusterInventory":
        return cls(
            guard=AuthorizationGuard(),
            reader=KubernetesResourceReader.from_env(),
        )

    def list(self, run_context) -> dict:
        span = trace.get_current_span()
        channel = extract_channel(run_context)
        chat_id = extract_chat_id(run_context)

        user_id, err = self._guard.check(channel, chat_id, span)
        if err is not None:
            return err

        try:
            items = self._reader.search_for_instance_of(
                CLUSTER_GROUP, CLUSTER_VERSION, CLUSTER_PLURAL
            )
            clusters = [
                {"name": i["metadata"]["name"], "status": _status_from_conditions(i)}
                for i in items
            ]
            return {"status": "ok", "clusters": clusters}
        except Exception:
            log.exception("list_cluster_instances failed")
            return {
                "status": "error",
                "message": "List failed. Please try again later.",
            }

    def get(self, name: str, run_context) -> dict:
        span = trace.get_current_span()
        channel = extract_channel(run_context)
        chat_id = extract_chat_id(run_context)

        user_id, err = self._guard.check(channel, chat_id, span)
        if err is not None:
            return err

        try:
            item = self._reader.get_by_name(
                CLUSTER_GROUP, CLUSTER_VERSION, CLUSTER_PLURAL, name
            )
            if item is None:
                return {
                    "status": "not_found",
                    "name": name,
                    "message": f"Nenhum Cluster encontrado com o nome {name}.",
                }
            status = _status_from_conditions(item)
            condition = _ready_condition(item)
            return {
                "status": status,
                "name": name,
                "message": _status_message(name, status, condition),
            }
        except Exception:
            log.exception("get_cluster_status failed")
            return {
                "status": "error",
                "message": "Status check failed. Please try again later.",
            }
```

Update `wasp/resources/cluster/__init__.py` — append:

```python
from wasp.resources.cluster.inventory import (
    ClusterInventory as ClusterInventory,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cluster_inventory.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add wasp/resources/cluster/inventory.py wasp/resources/cluster/__init__.py tests/test_cluster_inventory.py
git commit -m "feat(cluster): add Cluster inventory"
```

---

## Task 5: Cluster @tool wrappers in provision.py

**Files:**
- Modify: `wasp/provision.py`
- Test: `tests/test_provision.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_provision.py`:

```python
def test_provision_cluster_commits(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_cluster_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setenv("GITHUB_BASE_URL", "https://api.github.com")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr("wasp.watcher.threading.Thread", MagicMock())

    result = provision_cluster_instance(name="edge", requested_by="alice")

    call_kwargs = mock_client.create_file.call_args.kwargs
    assert call_kwargs["path"] == "infrastructure/clusters/edge.yaml"
    assert call_kwargs["branch"] == "dev"
    assert "feat(clusters): provision edge" in call_kwargs["message"]
    assert result["status"] == "provisioning"
    assert "edge" in result["message"]


def test_provision_cluster_creates_span(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    mock_client_cls = MagicMock()
    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setenv("GITHUB_BASE_URL", "https://api.github.com")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr("wasp.watcher.threading.Thread", MagicMock())

    from wasp.provision import provision_cluster_instance

    provision_cluster_instance(name="edge")

    spans = exporter.get_finished_spans()
    assert any(s.name == "provision_cluster_instance" for s in spans)


def test_list_cluster_instances_returns_clusters(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import list_cluster_instances

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "edge"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            },
        ]
    }
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = list_cluster_instances(run_context=FakeCtx())

    assert result == {
        "status": "ok",
        "clusters": [{"name": "edge", "status": "Ready"}],
    }


def test_list_cluster_instances_creates_span(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.return_value = {"items": []}
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    from wasp.provision import list_cluster_instances

    list_cluster_instances()

    spans = exporter.get_finished_spans()
    assert any(s.name == "list_cluster_instances" for s in spans)


def test_get_cluster_status_returns_status_and_message(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import get_cluster_status

    mock_api = MagicMock()
    mock_api.get_cluster_custom_object.return_value = {
        "metadata": {"name": "edge"},
        "status": {
            "conditions": [
                {
                    "type": "Ready",
                    "status": "True",
                    "lastTransitionTime": "2026-05-30T10:00:00Z",
                }
            ]
        },
    }
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = get_cluster_status(name="edge", run_context=FakeCtx())

    assert result["status"] == "Ready"
    assert result["name"] == "edge"
    assert result["message"] == "O Cluster edge está Ready desde 30/05."


def test_get_cluster_status_creates_span(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    mock_api = MagicMock()
    mock_api.get_cluster_custom_object.return_value = {
        "metadata": {"name": "edge"},
        "status": {"conditions": []},
    }
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    from wasp.provision import get_cluster_status

    get_cluster_status(name="edge")

    spans = exporter.get_finished_spans()
    assert any(s.name == "get_cluster_status" for s in spans)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_provision.py -k cluster -v`
Expected: FAIL with `ImportError: cannot import name 'provision_cluster_instance'`

- [ ] **Step 3: Add the @tool wrappers**

In `wasp/provision.py`, extend the import block:

```python
from wasp.resources.cluster import (
    DEFAULT_KUBERNETES_VERSION,
    ClusterInventory,
    ClusterProvisioner,
)
```

Then append at the end of `wasp/provision.py`:

```python
@tool
@telemetry.instrument("get_cluster_status")
def get_cluster_status(name: str, run_context=None) -> dict:
    """
    Returns the current status of a specific Cluster instance.
    Returns: {"status": "Ready"|"Pending"|"Unknown"|"not_found", "name": str, "message": str}.
    Read-only — safe to call without confirmation.
    """
    return ClusterInventory.from_env().get(name=name, run_context=run_context)


@tool
@telemetry.instrument("list_cluster_instances")
def list_cluster_instances(run_context=None) -> dict:
    """
    Lists all provisioned Cluster instances and their status.
    Returns: {"status": "ok", "clusters": [{"name": str, "status": "Ready"|"Pending"|"Unknown"}, ...]}.
    Read-only — safe to call without confirmation.
    """
    return ClusterInventory.from_env().list(run_context=run_context)


@tool
@telemetry.instrument("provision_cluster_instance")
def provision_cluster_instance(
    name: str,
    kubernetes_version: str = DEFAULT_KUBERNETES_VERSION,
    requested_by: str = "",
    run_context=None,
) -> dict:
    """
    Provisions a new Cluster instance by committing a Kubernetes manifest to a Git repository.

    Returns: status (provisioning|already_provisioning|unauthorized|error) + message.
    """
    return ClusterProvisioner.from_env().provision(
        name=name,
        kubernetes_version=kubernetes_version,
        requested_by=requested_by,
        run_context=run_context,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_provision.py -k cluster -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add wasp/provision.py tests/test_provision.py
git commit -m "feat(cluster): add Cluster @tool wrappers"
```

---

## Task 6: Cluster provider + registry registration

**Files:**
- Create: `wasp/resources/cluster/provider.py`
- Modify: `wasp/resources/registry.py:9-11` (the `PROVIDERS` list)
- Test: `tests/test_cluster_provider.py`
- Test: `tests/test_registry.py` (append — verify cluster is discovered)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cluster_provider.py`:

```python
def test_cluster_provider_name(mock_agno):
    from wasp.resources.cluster.provider import ClusterProvider

    assert ClusterProvider().name == "cluster"


def test_cluster_provider_tools(mock_agno):
    from wasp.provision import (
        get_cluster_status,
        list_cluster_instances,
        provision_cluster_instance,
    )
    from wasp.resources.cluster.provider import ClusterProvider

    tools = ClusterProvider().tools()

    assert tools == [
        provision_cluster_instance,
        list_cluster_instances,
        get_cluster_status,
    ]


def test_cluster_provider_satisfies_protocol(mock_agno):
    from wasp.resources.cluster.provider import ClusterProvider
    from wasp.resources.protocol import ResourceProvider

    assert isinstance(ClusterProvider(), ResourceProvider)
```

Check whether `tests/test_registry.py` exists. If it does, append the test below. If it does NOT exist, create it with this single test:

```python
def test_registry_discovers_cluster_provider(mock_agno):
    from wasp.resources.registry import ResourceRegistry

    registry = ResourceRegistry.discover()

    names = [p.name for p in registry._providers]
    assert "cluster" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cluster_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wasp.resources.cluster.provider'`

- [ ] **Step 3: Create the provider and register it**

Create `wasp/resources/cluster/provider.py`:

```python
from collections.abc import Callable

from wasp.provision import (
    get_cluster_status,
    list_cluster_instances,
    provision_cluster_instance,
)


class ClusterProvider:
    name = "cluster"

    def tools(self) -> list[Callable]:
        return [
            provision_cluster_instance,
            list_cluster_instances,
            get_cluster_status,
        ]
```

In `wasp/resources/registry.py`, extend the `PROVIDERS` list:

```python
PROVIDERS = [
    "wasp.resources.platform.provider:PlatformProvider",
    "wasp.resources.cluster.provider:ClusterProvider",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cluster_provider.py tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add wasp/resources/cluster/provider.py wasp/resources/registry.py tests/test_cluster_provider.py tests/test_registry.py
git commit -m "feat(cluster): register ClusterProvider in registry"
```

---

## Task 7: Register cluster modules in mock_agno fixture

**Files:**
- Modify: `tests/conftest.py` (both the setup loop ~lines 55-99 and the teardown loop ~lines 150-194)

- [ ] **Step 1: Add cluster modules to both sys.modules.pop loops**

In `tests/conftest.py`, both the setup and teardown loops contain this line:

```python
        "wasp.resources.platform.provider",
```

Immediately after that line, in BOTH loops, add:

```python
        "wasp.resources.cluster",
        "wasp.resources.cluster.manifest",
        "wasp.resources.cluster.inventory",
        "wasp.resources.cluster.provisioner",
        "wasp.resources.cluster.provider",
```

- [ ] **Step 2: Run the full suite (no Docker-gated subset) to confirm no state leak**

Run: `pytest tests/ -p no:cacheprovider -q --no-cov -k "cluster or platform or registry or provision"`
Expected: all PASS, no intermittent failures across repeated runs.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(cluster): register cluster modules in mock_agno fixture"
```

---

## Task 8: Documentation + full validation

**Files:**
- Modify: `docs/architecture/platform-provisioning.md` (add a short Cluster note) OR create `docs/architecture/cluster-provisioning.md`
- Modify: `CLAUDE.md` (the `wasp/resources/` section already documents the pattern; update the "Próximo CRD: Cluster" example if it references future work)
- Modify: `HANDOFF.md` (mark Cluster done; remove from Backlog)
- Modify: `docs/sdlc/02-design/2026-06-02-cluster-crd.md` (set `Status: Implemented`)

- [ ] **Step 1: Update the design spec status**

In `docs/sdlc/02-design/2026-06-02-cluster-crd.md`, change `**Status:** Approved` to `**Status:** Implemented`.

- [ ] **Step 2: Add architecture note**

Create `docs/architecture/cluster-provisioning.md`:

```markdown
# Cluster provisioning

- GitOps repo path: `infrastructure/clusters/{name}.yaml`.
- CRD: `apiVersion: wasp.silvios.me/v1alpha1`, `kind: Cluster`. Uses standard Kubernetes `metadata.name`.
- Spec: `kubernetesVersion` (default `1.34`). Crossplane Composition reconciles the Cluster into a ConfigMap.
- Tools: `provision_cluster_instance`, `list_cluster_instances`, `get_cluster_status` (in `wasp/provision.py`).
- Watcher: `watch_cluster` + `ClusterWatcherSpawner` in `wasp/watcher.py` — polls the `Ready` condition and notifies on success or timeout.
- Follows the same pattern as Platform (see `platform-provisioning.md`). No generic watcher abstraction — revisit if a third CRD arrives.
```

- [ ] **Step 3: Update HANDOFF.md**

Remove the Backlog line `- **Próximo CRD: \`Cluster\`** ...` and add a "Why" entry summarizing the Cluster CRD as done.

- [ ] **Step 4: Run formatter and linter**

Run: `make format`
Expected: ruff format + ruff check pass with no errors.

If ruff flags the unused `DEFAULT_KUBERNETES_VERSION` import in `wasp/resources/cluster/provisioner.py` (F401), remove that import line and re-run.

- [ ] **Step 5: Run full test suite with coverage**

Run: `make test`
Expected: all tests pass, coverage 100%.

If coverage is below 100%, run `pytest --cov --cov-report=term-missing` and add tests for the uncovered lines before proceeding.

- [ ] **Step 6: Run E2E**

Run: `make e2e-with-debug`
Expected: PASS. (Cluster has no E2E fixture yet; this confirms the existing Platform flow still works after the watcher.py changes.)

- [ ] **Step 7: Commit**

```bash
git add docs/architecture/cluster-provisioning.md docs/sdlc/02-design/2026-06-02-cluster-crd.md HANDOFF.md CLAUDE.md
git commit -m "docs(cluster): document Cluster provisioning and mark spec implemented"
```

---

## Self-Review checklist (completed by plan author)

- **Spec coverage:** manifest (T1), provisioner (T2), watcher (T3), inventory (T4), tools (T5), provider+registry (T6), conftest (T7), docs (T8). All spec sections covered.
- **Circular import note:** `provider.py` imports from `wasp.provision`, which imports from `wasp.resources.cluster` (`__init__`). This matches the Platform pattern exactly — `provider.py` is a leaf module NOT re-exported in `__init__.py`, avoiding the cycle. Do not add `provider` to `__init__.py`.
- **Watcher dependency:** Task 2 (provisioner) imports `ClusterWatcherSpawner` from Task 3 (watcher). Flagged inline in Task 2 Step 4. Recommended execution order: T1 → T3 → T2 → T4 → T5 → T6 → T7 → T8, OR write all failing tests first then implement. Subagent-driven execution should respect this dependency.
- **Type consistency:** `ClusterManifest.build(name, kubernetes_version)`, `ClusterSpec.kubernetesVersion`, `ClusterProvisioner.provision(name, kubernetes_version, requested_by, run_context)`, `ClusterInventory.list/get`, `cluster_ready_message(name, cluster)` — consistent across all tasks.
- **Return key naming:** inventory `list` returns `"clusters"` (not `"tenants"`) — verified in T4 tests and T5 tool docstring.
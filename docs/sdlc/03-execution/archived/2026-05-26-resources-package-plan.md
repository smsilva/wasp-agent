# Resources Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract Platform-specific code from `wasp/provision.py` into `wasp/resources/platform/`, introduce a generic Kubernetes reader at `wasp/clients/k8s/`, and prepare for the upcoming `Cluster` CRD.

**Architecture:** Two new packages — `wasp/resources/` (CRD definitions, one subpackage per kind) and `wasp/clients/k8s/` (generic Kubernetes client). `wasp/provision.py` becomes a thin facade of `@tool` registrations. `wasp/platform_cluster.py` is removed; its generic part becomes `KubernetesResourceReader.search_for_instance_of`, its Platform-specific part lives in `PlatformInventory`.

**Tech Stack:** Python 3.14, Pydantic, kubernetes-client, pytest, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-05-26-resources-package-design.md`

---

## File map

```
wasp/resources/__init__.py            ← new — re-export ResourceManifest, MetadataSpec
wasp/resources/base.py                ← new — ResourceManifest, MetadataSpec, WASP_API_VERSION
wasp/resources/platform/__init__.py   ← new — re-export public classes
wasp/resources/platform/manifest.py   ← new — PlatformManifest, specs, PLATFORM_* constants
wasp/resources/platform/inventory.py  ← new — PlatformInventory + _status_from_conditions
wasp/resources/platform/provisioner.py← new — PlatformProvisioner + DEFAULT_DOMAIN/REGIONS

wasp/clients/k8s/__init__.py          ← new — load_kube_config_auto + re-export KubernetesResourceReader
wasp/clients/k8s/reader.py            ← new — KubernetesResourceReader

wasp/provision.py                     ← rewrite — only @tool wrappers
wasp/platform_cluster.py              ← DELETED
wasp/watcher.py                       ← drop PLATFORM_* constants + load_kube_config_auto (import from new locations)

tests/test_platform_cluster.py        ← rename → tests/test_k8s_reader.py (rewritten for generic reader)
tests/test_platform_inventory.py      ← new — covers _status_from_conditions and PlatformInventory.list
tests/test_provision.py               ← update imports + monkeypatch paths
tests/conftest.py                     ← update sys.modules.pop list
```

---

## Task 1: ResourceManifest base class

Create the generic base that all CRD manifests inherit from.

**Files:**
- Create: `wasp/resources/__init__.py`
- Create: `wasp/resources/base.py`
- Create: `tests/test_resource_manifest.py`

- [ ] **Step 1: Write failing tests for the base class**

Create `tests/test_resource_manifest.py`:

```python
def test_resource_manifest_default_api_version():
    from wasp.resources.base import MetadataSpec, ResourceManifest

    class FakeSpec(ResourceManifest):
        kind: str = "Fake"
        spec: dict = {}

    m = FakeSpec(metadata=MetadataSpec(name="x"))
    assert m.apiVersion == "wasp.silvios.me/v1alpha1"
    assert m.metadata.name == "x"
    assert m.kind == "Fake"


def test_resource_manifest_exposes_constant():
    from wasp.resources.base import WASP_API_VERSION

    assert WASP_API_VERSION == "wasp.silvios.me/v1alpha1"


def test_resources_package_reexports():
    from wasp.resources import MetadataSpec, ResourceManifest

    assert ResourceManifest.__name__ == "ResourceManifest"
    assert MetadataSpec.__name__ == "MetadataSpec"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_resource_manifest.py -v
```

Expected: 3 failures with `ModuleNotFoundError: No module named 'wasp.resources'`.

- [ ] **Step 3: Implement `wasp/resources/base.py`**

```python
from pydantic import BaseModel

WASP_API_VERSION = "wasp.silvios.me/v1alpha1"


class MetadataSpec(BaseModel):
    name: str


class ResourceManifest(BaseModel):
    apiVersion: str = WASP_API_VERSION
    metadata: MetadataSpec
```

- [ ] **Step 4: Create `wasp/resources/__init__.py`**

```python
from wasp.resources.base import MetadataSpec as MetadataSpec
from wasp.resources.base import ResourceManifest as ResourceManifest
from wasp.resources.base import WASP_API_VERSION as WASP_API_VERSION
```

(The `X as X` form silences ruff F401.)

- [ ] **Step 5: Run tests, verify they pass**

```bash
uv run pytest tests/test_resource_manifest.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Run full suite to confirm nothing else broke**

```bash
make test
```

Expected: all pass, coverage unchanged.

- [ ] **Step 7: Lint and commit**

```bash
make format
uv run ruff check .
git add wasp/resources/ tests/test_resource_manifest.py
git commit -m "$(cat <<'EOF'
feat(resources): add ResourceManifest base for CRD manifests

New wasp/resources/ package introduces ResourceManifest, MetadataSpec,
and WASP_API_VERSION. Subclasses will define kind + spec. First
consumer (PlatformManifest) follows in the next commit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Move PlatformManifest into `wasp/resources/platform/`

Move `PlatformManifest`, `PlatformSpec`, `RegionSpec`, `ServiceSpec` and the `PLATFORM_GROUP/VERSION/PLURAL` constants out of `wasp/provision.py` and `wasp/watcher.py`. `PlatformManifest` inherits from `ResourceManifest`.

**Files:**
- Create: `wasp/resources/platform/__init__.py`
- Create: `wasp/resources/platform/manifest.py`
- Modify: `wasp/provision.py` (remove moved classes)
- Modify: `wasp/watcher.py` (remove `PLATFORM_*` constants, import from new location)
- Modify: `tests/test_provision.py` (update import path)
- Modify: `tests/conftest.py` (add new modules to `sys.modules.pop` list)

- [ ] **Step 1: Create `wasp/resources/platform/manifest.py`**

```python
from pydantic import BaseModel, Field

from wasp.resources.base import MetadataSpec, ResourceManifest

PLATFORM_GROUP = "wasp.silvios.me"
PLATFORM_VERSION = "v1alpha1"
PLATFORM_PLURAL = "platforms"


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


class PlatformManifest(ResourceManifest):
    kind: str = "Platform"
    spec: PlatformSpec

    @classmethod
    def build(cls, name: str, domain: str, regions: list[str]) -> "PlatformManifest":
        return cls(
            metadata=MetadataSpec(name=name),
            spec=PlatformSpec(
                domain=domain,
                regions=[
                    RegionSpec(name=r, endpoint=f"gateway.{r}.{name}.{domain}")
                    for r in regions
                ],
            ),
        )
```

- [ ] **Step 2: Create `wasp/resources/platform/__init__.py`**

```python
from wasp.resources.platform.manifest import (
    PLATFORM_GROUP as PLATFORM_GROUP,
)
from wasp.resources.platform.manifest import (
    PLATFORM_PLURAL as PLATFORM_PLURAL,
)
from wasp.resources.platform.manifest import (
    PLATFORM_VERSION as PLATFORM_VERSION,
)
from wasp.resources.platform.manifest import (
    PlatformManifest as PlatformManifest,
)
```

- [ ] **Step 3: Remove moved classes from `wasp/provision.py`**

In `wasp/provision.py`, delete:
- `class ServiceSpec`
- `class RegionSpec`
- `class PlatformSpec`
- `class MetadataSpec`
- `class PlatformManifest`
- The unused imports they leave behind (`from pydantic import BaseModel, Field`)

Leave the `yaml` import in place — `PlatformProvisioner` still uses it for now.

- [ ] **Step 4: Import `PlatformManifest` back into `wasp/provision.py` for `PlatformProvisioner`**

Near the top of `wasp/provision.py`, add:

```python
from wasp.resources.platform import PlatformManifest
```

`PlatformProvisioner.provision()` continues to call `PlatformManifest.build(...)`.

- [ ] **Step 5: Remove `PLATFORM_*` constants from `wasp/watcher.py`**

In `wasp/watcher.py`, delete the three lines:

```python
PLATFORM_GROUP = "wasp.silvios.me"
PLATFORM_VERSION = "v1alpha1"
PLATFORM_PLURAL = "platforms"
```

Add an import near the top:

```python
from wasp.resources.platform import PLATFORM_GROUP, PLATFORM_PLURAL, PLATFORM_VERSION
```

- [ ] **Step 6: Update `tests/test_provision.py` imports**

Replace:

```python
from wasp.provision import PlatformManifest
```

with:

```python
from wasp.resources.platform import PlatformManifest
```

in both `test_manifest_build` and `test_manifest_yaml_output`. The other tests in `test_provision.py` already import `provision_platform_instance` / `list_platform_instances` (not the manifest) — leave those alone.

- [ ] **Step 7: Update `tests/conftest.py` — add new modules to BOTH `sys.modules.pop` loops**

In both the pre-test and post-test `sys.modules.pop` loops, add these entries (alongside the existing wasp modules):

```python
        "wasp.resources",
        "wasp.resources.base",
        "wasp.resources.platform",
        "wasp.resources.platform.manifest",
```

- [ ] **Step 8: Run `make test` — all green**

```bash
make test
```

Expected: all tests pass, coverage 100%.

- [ ] **Step 9: Lint and commit**

```bash
make format
uv run ruff check .
git add wasp/resources/platform/ wasp/provision.py wasp/watcher.py tests/test_provision.py tests/conftest.py
git commit -m "$(cat <<'EOF'
refactor(resources): move PlatformManifest into wasp/resources/platform

PlatformManifest now inherits from ResourceManifest. PLATFORM_GROUP/
VERSION/PLURAL constants move from wasp.watcher to
wasp.resources.platform.manifest, where they conceptually belong.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Generic KubernetesResourceReader

Create `wasp/clients/k8s/` with a generic reader that any future CRD can use.

**Files:**
- Create: `wasp/clients/k8s/__init__.py`
- Create: `wasp/clients/k8s/reader.py`
- Create: `tests/test_k8s_reader.py`
- Modify: `wasp/watcher.py` (remove local `load_kube_config_auto`, import from new location)
- Modify: `tests/conftest.py`
- Delete (later): `tests/test_platform_cluster.py` (replaced by `tests/test_k8s_reader.py`)

- [ ] **Step 1: Write failing tests for `KubernetesResourceReader`**

Create `tests/test_k8s_reader.py`:

```python
from unittest.mock import MagicMock


def test_search_for_instance_of_empty():
    from wasp.clients.k8s import KubernetesResourceReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {"items": []}

    result = KubernetesResourceReader(api=api).search_for_instance_of(
        group="wasp.silvios.me", version="v1alpha1", plural="platforms"
    )

    assert result == []


def test_search_for_instance_of_returns_raw_items():
    from wasp.clients.k8s import KubernetesResourceReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {
        "items": [
            {"metadata": {"name": "acme"}, "status": {"conditions": []}},
            {"metadata": {"name": "globex"}},
        ]
    }

    result = KubernetesResourceReader(api=api).search_for_instance_of(
        group="wasp.silvios.me", version="v1alpha1", plural="platforms"
    )

    assert result == [
        {"metadata": {"name": "acme"}, "status": {"conditions": []}},
        {"metadata": {"name": "globex"}},
    ]


def test_search_for_instance_of_calls_api_with_args():
    from wasp.clients.k8s import KubernetesResourceReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {"items": []}

    KubernetesResourceReader(api=api).search_for_instance_of(
        group="example.com", version="v2", plural="widgets"
    )

    api.list_cluster_custom_object.assert_called_once_with(
        group="example.com", version="v2", plural="widgets"
    )


def test_from_env_uses_kube_config(monkeypatch):
    from wasp.clients.k8s import KubernetesResourceReader

    mock_api = MagicMock()
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    reader = KubernetesResourceReader.from_env()

    assert reader._api is mock_api


def test_load_kube_config_auto_incluster(monkeypatch):
    import wasp.clients.k8s as k8s

    monkeypatch.setattr(k8s.config, "load_incluster_config", lambda: None)
    monkeypatch.setattr(k8s.config, "load_kube_config", MagicMock())
    monkeypatch.setattr(k8s.client, "CustomObjectsApi", MagicMock())

    k8s.load_kube_config_auto()

    k8s.config.load_kube_config.assert_not_called()


def test_load_kube_config_auto_fallback_local(monkeypatch):
    import wasp.clients.k8s as k8s

    def raise_config():
        raise k8s.config.ConfigException("no in-cluster")

    monkeypatch.setattr(k8s.config, "load_incluster_config", raise_config)
    monkeypatch.setattr(k8s.config, "load_kube_config", MagicMock())
    monkeypatch.setattr(k8s.client, "CustomObjectsApi", MagicMock())

    k8s.load_kube_config_auto()

    k8s.config.load_kube_config.assert_called_once()
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_k8s_reader.py -v
```

Expected: failures — `ModuleNotFoundError: No module named 'wasp.clients.k8s'`.

- [ ] **Step 3: Create `wasp/clients/k8s/reader.py`**

```python
from kubernetes.client import CustomObjectsApi

from wasp.clients.k8s import load_kube_config_auto


class KubernetesResourceReader:
    def __init__(self, api: CustomObjectsApi):
        self._api = api

    @classmethod
    def from_env(cls) -> "KubernetesResourceReader":
        return cls(api=load_kube_config_auto())

    def search_for_instance_of(
        self, group: str, version: str, plural: str
    ) -> list[dict]:
        result = self._api.list_cluster_custom_object(
            group=group, version=version, plural=plural
        )
        return result.get("items", [])
```

- [ ] **Step 4: Create `wasp/clients/k8s/__init__.py`**

`load_kube_config_auto` is defined **before** the reader re-export so `reader.py` can import it without a circular failure.

```python
from kubernetes import client, config


def load_kube_config_auto() -> "client.CustomObjectsApi":
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CustomObjectsApi()


from wasp.clients.k8s.reader import (  # noqa: E402
    KubernetesResourceReader as KubernetesResourceReader,
)
```

- [ ] **Step 5: Update `wasp/watcher.py` to import `load_kube_config_auto` from the new location**

Remove the local definition (lines 43-48 of the original file):

```python
def load_kube_config_auto() -> "client.CustomObjectsApi":
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CustomObjectsApi()
```

Remove `from kubernetes import client, config` — these names were only used by `load_kube_config_auto`. **Keep** `from kubernetes.client import ApiException` — still used in `_watch_platform_inner`.

Add the new import:

```python
from wasp.clients.k8s import load_kube_config_auto
```

After the edit, the imports block of `wasp/watcher.py` should contain:

```python
from kubernetes.client import ApiException

from wasp.clients.k8s import load_kube_config_auto
from wasp.resources.platform import PLATFORM_GROUP, PLATFORM_PLURAL, PLATFORM_VERSION
```

Verify the watcher still calls `load_kube_config_auto()` on line that was 106 — no rename needed because the imported name is identical.

- [ ] **Step 6: Update `tests/conftest.py` `sys.modules.pop` loops**

Add to both loops:

```python
        "wasp.clients.k8s",
        "wasp.clients.k8s.reader",
```

- [ ] **Step 7: Run `make test`**

```bash
make test
```

Expected: `test_k8s_reader.py` passes (6 tests). `test_watcher.py` still passes — its 8 `monkeypatch.setattr(w, "load_kube_config_auto", …)` calls still work because `from wasp.clients.k8s import load_kube_config_auto` rebinds the name into `wasp.watcher`'s namespace. `test_platform_cluster.py` still passes (we haven't touched it yet).

- [ ] **Step 8: Lint and commit**

```bash
make format
uv run ruff check .
git add wasp/clients/k8s/ wasp/watcher.py tests/test_k8s_reader.py tests/conftest.py
git commit -m "$(cat <<'EOF'
feat(clients/k8s): add generic KubernetesResourceReader

New wasp/clients/k8s/ package exposes load_kube_config_auto (moved
from wasp.watcher) and KubernetesResourceReader, a CRD-agnostic
reader that takes (group, version, plural) and returns raw items.

PlatformInventory will switch to this reader in the next commit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Move PlatformInventory and switch to the generic reader

Move `PlatformInventory` and `_status_from_conditions` to `wasp/resources/platform/inventory.py`, replace `PlatformClusterReader` with `KubernetesResourceReader`. Add the dedicated test file.

**Files:**
- Create: `wasp/resources/platform/inventory.py`
- Create: `tests/test_platform_inventory.py`
- Modify: `wasp/resources/platform/__init__.py` (re-export `PlatformInventory`)
- Modify: `wasp/provision.py` (import inventory from new location)
- Modify: `tests/test_provision.py` (update 4 monkeypatch paths)
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests in `tests/test_platform_inventory.py`**

```python
from unittest.mock import MagicMock


def test_status_from_conditions_ready():
    from wasp.resources.platform.inventory import _status_from_conditions

    platform = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
    assert _status_from_conditions(platform) == "Ready"


def test_status_from_conditions_pending():
    from wasp.resources.platform.inventory import _status_from_conditions

    platform = {"status": {"conditions": [{"type": "Ready", "status": "False"}]}}
    assert _status_from_conditions(platform) == "Pending"


def test_status_from_conditions_unknown_when_missing():
    from wasp.resources.platform.inventory import _status_from_conditions

    assert _status_from_conditions({"status": {"conditions": []}}) == "Unknown"
    assert _status_from_conditions({}) == "Unknown"


def test_inventory_list_transforms_items():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    reader.search_for_instance_of.return_value = [
        {
            "metadata": {"name": "acme"},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        },
        {
            "metadata": {"name": "globex"},
            "status": {"conditions": [{"type": "Ready", "status": "False"}]},
        },
        {"metadata": {"name": "fresh"}, "status": {}},
    ]
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = PlatformInventory(guard=guard, reader=reader).list(FakeCtx())

    assert result == {
        "status": "ok",
        "tenants": [
            {"name": "acme", "status": "Ready"},
            {"name": "globex", "status": "Pending"},
            {"name": "fresh", "status": "Unknown"},
        ],
    }


def test_inventory_list_calls_reader_with_platform_gvp():
    from wasp.resources.platform.inventory import PlatformInventory
    from wasp.resources.platform.manifest import (
        PLATFORM_GROUP,
        PLATFORM_PLURAL,
        PLATFORM_VERSION,
    )

    reader = MagicMock()
    reader.search_for_instance_of.return_value = []
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    PlatformInventory(guard=guard, reader=reader).list(FakeCtx())

    reader.search_for_instance_of.assert_called_once_with(
        PLATFORM_GROUP, PLATFORM_VERSION, PLATFORM_PLURAL
    )


def test_inventory_list_returns_unauthorized_when_guard_denies():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    guard = MagicMock()
    guard.check.return_value = (
        None,
        {"status": "unauthorized", "message": "Acesso negado."},
    )

    class FakeCtx:
        session_id = "tg:wasp-agent:999"

    result = PlatformInventory(guard=guard, reader=reader).list(FakeCtx())

    assert result == {"status": "unauthorized", "message": "Acesso negado."}
    reader.search_for_instance_of.assert_not_called()


def test_inventory_list_returns_error_on_exception():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    reader.search_for_instance_of.side_effect = RuntimeError("boom")
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = PlatformInventory(guard=guard, reader=reader).list(FakeCtx())

    assert result["status"] == "error"
    assert result["message"] == "List failed. Please try again later."
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_platform_inventory.py -v
```

Expected: 7 failures with `ModuleNotFoundError: No module named 'wasp.resources.platform.inventory'`.

- [ ] **Step 3: Create `wasp/resources/platform/inventory.py`**

```python
import logging

from opentelemetry import trace

from wasp.auth_guard import AuthorizationGuard
from wasp.clients.k8s import KubernetesResourceReader
from wasp.resources.platform.manifest import (
    PLATFORM_GROUP,
    PLATFORM_PLURAL,
    PLATFORM_VERSION,
)
from wasp.watcher import extract_channel, extract_chat_id

log = logging.getLogger(__name__)


def _status_from_conditions(platform: dict) -> str:
    for c in platform.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return "Ready" if c.get("status") == "True" else "Pending"
    return "Unknown"


class PlatformInventory:
    def __init__(
        self,
        guard: AuthorizationGuard,
        reader: KubernetesResourceReader,
    ):
        self._guard = guard
        self._reader = reader

    @classmethod
    def from_env(cls) -> "PlatformInventory":
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
                PLATFORM_GROUP, PLATFORM_VERSION, PLATFORM_PLURAL
            )
            tenants = [
                {"name": i["metadata"]["name"], "status": _status_from_conditions(i)}
                for i in items
            ]
            return {"status": "ok", "tenants": tenants}
        except Exception:
            log.exception("list_platform_instances failed")
            return {
                "status": "error",
                "message": "List failed. Please try again later.",
            }
```

- [ ] **Step 4: Re-export from `wasp/resources/platform/__init__.py`**

Add to the existing `__init__.py`:

```python
from wasp.resources.platform.inventory import (
    PlatformInventory as PlatformInventory,
)
```

- [ ] **Step 5: Update `wasp/provision.py` to delete the old `PlatformInventory` and import from new location**

In `wasp/provision.py`:

- Delete `class PlatformInventory: …` (and its `from_env` and `list`).
- Delete the `_status_from_conditions` function if it was duplicated (it was only in `wasp/platform_cluster.py`; `provision.py` does not have it — so nothing to delete here, just confirm).
- Delete `from wasp.platform_cluster import PlatformClusterReader`.
- Add: `from wasp.resources.platform import PlatformInventory`.

Verify the `@tool` function `list_platform_instances` still calls `PlatformInventory.from_env().list(run_context=run_context)` — the import path changed but the API is identical.

- [ ] **Step 6: Update the 4 monkeypatch paths in `tests/test_provision.py`**

Find these four lines (one in each of `test_list_returns_tenants_with_status`, `test_list_returns_empty_list`, `test_list_returns_error_on_exception`, `test_list_creates_span`):

```python
monkeypatch.setattr("wasp.platform_cluster.load_kube_config_auto", lambda: mock_api)
```

Replace each with:

```python
monkeypatch.setattr("wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api)
```

(The reader does `from wasp.clients.k8s import load_kube_config_auto`, so the attribute lives at `wasp.clients.k8s.reader.load_kube_config_auto`.)

- [ ] **Step 7: Update `tests/conftest.py` `sys.modules.pop` loops**

Add to both loops:

```python
        "wasp.resources.platform.inventory",
```

- [ ] **Step 8: Run `make test`**

```bash
make test
```

Expected: all pass. The old `test_platform_cluster.py` is still around — it'll still pass because we haven't deleted `wasp/platform_cluster.py` yet.

- [ ] **Step 9: Lint and commit**

```bash
make format
uv run ruff check .
git add wasp/resources/platform/inventory.py wasp/resources/platform/__init__.py wasp/provision.py tests/test_platform_inventory.py tests/test_provision.py tests/conftest.py
git commit -m "$(cat <<'EOF'
refactor(resources): move PlatformInventory to wasp/resources/platform

PlatformInventory now uses KubernetesResourceReader instead of
PlatformClusterReader. The status-from-conditions transformation
travels with PlatformInventory; the cluster reader stays generic.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Move PlatformProvisioner and add `requested_by` fallback

Move `PlatformProvisioner`, `DEFAULT_DOMAIN`, `DEFAULT_REGIONS` to `wasp/resources/platform/provisioner.py`. Add the fallback: when `requested_by` is empty, use the auth-resolved `user_id`.

**Files:**
- Create: `wasp/resources/platform/provisioner.py`
- Modify: `wasp/resources/platform/__init__.py` (re-export `PlatformProvisioner`)
- Modify: `wasp/provision.py` (import provisioner from new location)
- Modify: `tests/test_provision.py` (add a test for the fallback)
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing test for the `requested_by` fallback**

Append to `tests/test_provision.py`:

```python
def test_provision_defaults_requested_by_to_user_id(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr(
        "wasp.auth.is_authorized", lambda channel, channel_id: "user-abc"
    )

    class FakeCtx:
        session_id = "tg:wasp-agent:5621932873"

    with patch("wasp.watcher.threading.Thread", MagicMock()):
        provision_platform_instance(
            name="wp2",
            domain="wasp.silvios.me",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    msg = mock_client.create_file.call_args.kwargs["message"]
    assert "Requested by: user-abc" in msg


def test_provision_defaults_requested_by_to_local_operator(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    with patch("wasp.watcher.threading.Thread", MagicMock()):
        provision_platform_instance(
            name="wp2",
            domain="wasp.silvios.me",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    msg = mock_client.create_file.call_args.kwargs["message"]
    assert "Requested by: local-operator" in msg


def test_provision_defaults_requested_by_to_unknown_without_context(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr("wasp.watcher.threading.Thread", MagicMock())

    provision_platform_instance(name="wp2")

    msg = mock_client.create_file.call_args.kwargs["message"]
    assert "Requested by: unknown" in msg
```

- [ ] **Step 2: Run the new tests, verify they fail**

```bash
uv run pytest tests/test_provision.py::test_provision_defaults_requested_by_to_user_id tests/test_provision.py::test_provision_defaults_requested_by_to_local_operator tests/test_provision.py::test_provision_defaults_requested_by_to_unknown_without_context -v
```

Expected: 3 failures — commit message contains `"Requested by: "` (empty) instead of the fallback values.

- [ ] **Step 3: Create `wasp/resources/platform/provisioner.py`**

```python
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
```

- [ ] **Step 4: Re-export from `wasp/resources/platform/__init__.py`**

Append:

```python
from wasp.resources.platform.provisioner import (
    DEFAULT_DOMAIN as DEFAULT_DOMAIN,
)
from wasp.resources.platform.provisioner import (
    DEFAULT_REGIONS as DEFAULT_REGIONS,
)
from wasp.resources.platform.provisioner import (
    PlatformProvisioner as PlatformProvisioner,
)
```

- [ ] **Step 5: Update `wasp/provision.py`**

Replace the entire file with the slim facade. Final content:

```python
from agno.tools import tool

import wasp.telemetry as telemetry
from wasp.resources.platform import (
    DEFAULT_DOMAIN,
    DEFAULT_REGIONS,
    PlatformInventory,
    PlatformProvisioner,
)


@tool
@telemetry.instrument("list_platform_instances")
def list_platform_instances(run_context=None) -> dict:
    """
    Lists all provisioned platform instances and their cluster status.
    Returns: {"status": "ok", "tenants": [{"name": str, "status": "Ready"|"Pending"|"Unknown"}, ...]}.
    Read-only — safe to call without confirmation.
    """
    return PlatformInventory.from_env().list(run_context=run_context)


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
```

- [ ] **Step 6: Update `tests/conftest.py` `sys.modules.pop` loops**

Add to both loops:

```python
        "wasp.resources.platform.provisioner",
```

- [ ] **Step 7: Run `make test`**

```bash
make test
```

Expected: all pass, including the 3 new fallback tests. Coverage 100%.

- [ ] **Step 8: Lint and commit**

```bash
make format
uv run ruff check .
git add wasp/resources/platform/provisioner.py wasp/resources/platform/__init__.py wasp/provision.py tests/test_provision.py tests/conftest.py
git commit -m "$(cat <<'EOF'
refactor(resources): move PlatformProvisioner to wasp/resources/platform

provision.py reduces to two @tool wrappers. PlatformProvisioner now
defaults requested_by to the auth-resolved user_id (or "unknown"),
so commit messages always identify the requester.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Delete `wasp/platform_cluster.py` and update conftest

The Platform-specific cluster reader is fully replaced. Remove the file and its test, drop the now-stale entries from `conftest.py`.

**Files:**
- Delete: `wasp/platform_cluster.py`
- Delete: `tests/test_platform_cluster.py`
- Modify: `tests/conftest.py` (remove `wasp.platform_cluster` from both pop loops)

- [ ] **Step 1: Verify nothing still imports `wasp.platform_cluster`**

```bash
grep -rn "wasp.platform_cluster" wasp/ tests/ main.py
```

Expected: only `tests/conftest.py` and `tests/test_platform_cluster.py` should match. If anything else matches, fix it before deleting.

- [ ] **Step 2: Delete the files**

```bash
git rm wasp/platform_cluster.py tests/test_platform_cluster.py
```

- [ ] **Step 3: Update `tests/conftest.py` — remove `wasp.platform_cluster` from both `sys.modules.pop` loops**

Remove this line (appears twice):

```python
        "wasp.platform_cluster",
```

- [ ] **Step 4: Run `make test`**

```bash
make test
```

Expected: all pass.

- [ ] **Step 5: Run ruff and final cleanup**

```bash
make format
uv run ruff check .
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py
git commit -m "$(cat <<'EOF'
refactor: drop wasp/platform_cluster.py (replaced by k8s reader)

PlatformClusterReader is fully superseded by KubernetesResourceReader
(generic) + the transformation in PlatformInventory.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update CLAUDE.md with the new package pattern

Document the `wasp/resources/<crd>/` pattern alongside the existing `wasp/clients/<channel>/` pattern, so the next CRD (Cluster) follows the same shape.

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate the "Packages" section**

```bash
grep -n "Packages" CLAUDE.md
```

Expected: a section header like `### Packages — wasp/clients/`.

- [ ] **Step 2: Add a sibling subsection for `wasp/resources/`**

After the existing `wasp/clients/` block, append a new block describing the resources package. Use this exact content:

````markdown
### Packages — `wasp/resources/`

CRD definitions live in `wasp/resources/<kind>/`:

```
wasp/resources/
  base.py              ← ResourceManifest base, MetadataSpec
  platform/
    manifest.py        ← PlatformManifest + group/version/plural constants
    provisioner.py     ← PlatformProvisioner
    inventory.py       ← PlatformInventory + status transformation
```

`wasp/provision.py` is the agent-tool facade — only `@tool` wrappers; lógica vive em `wasp/resources/`. Generic Kubernetes access goes through `wasp/clients/k8s/KubernetesResourceReader.search_for_instance_of(group, version, plural)`.

New CRD (e.g., Cluster): create `wasp/resources/cluster/{manifest,provisioner,inventory}.py`, add `@tool provision_cluster_instance` and `@tool list_cluster_instances` to `wasp/provision.py`.
````

- [ ] **Step 3: Run lint to confirm CLAUDE.md is not parsed**

```bash
uv run ruff check .
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(CLAUDE.md): document wasp/resources/<crd>/ pattern

Next CRD (Cluster) will follow the same layout: manifest, provisioner,
inventory under wasp/resources/cluster/.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Full validation

Run the mandatory three-step validation gate from CLAUDE.md before merging.

- [ ] **Step 1: Format**

```bash
make format
```

Expected: ruff reformats (or no changes).

- [ ] **Step 2: Unit + integration tests**

```bash
make test
```

Expected: all pass, coverage 100%.

- [ ] **Step 3: E2E with debug**

```bash
make e2e-with-debug
```

Expected: e2e suite passes. Watch for any failures related to imports — e.g., if `wasp.watcher` still references `PLATFORM_*` directly the e2e fake reconciler may fail at first call.

- [ ] **Step 4: Verify final `wasp/provision.py` is the slim facade**

```bash
wc -l wasp/provision.py
```

Expected: under 40 lines (was 227).

- [ ] **Step 5: Verify final file tree**

```bash
ls wasp/resources/ wasp/resources/platform/ wasp/clients/k8s/
```

Expected:
```
wasp/resources/:
__init__.py  base.py  platform

wasp/resources/platform/:
__init__.py  inventory.py  manifest.py  provisioner.py

wasp/clients/k8s/:
__init__.py  reader.py
```

- [ ] **Step 6: Verify `wasp/platform_cluster.py` is gone**

```bash
test ! -f wasp/platform_cluster.py && echo "OK"
```

Expected: `OK`.

- [ ] **Step 7: Push the branch (optional, ask user first)**

Don't push without explicit user approval.

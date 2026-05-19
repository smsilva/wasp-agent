# Platform Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `provision_platform_instance` agno tool that extracts parameters from natural language, requires user confirmation, and commits a Crossplane manifest to `smsilva/wasp-gitops`.

**Architecture:** A `tools/` package holds Pydantic models for the manifest and the tool function; `main.py` imports and registers the tool with the Agent. No changes to AgentOS, session storage, or existing test structure beyond wiring.

**Tech Stack:** PyGithub 2.x (commit to GitHub), pyyaml 6.x (manifest serialization), Pydantic 2.x (manifest models, already available via agno), agno 2.6.5 `@tool` decorator.

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add PyGithub and pyyaml to `pyproject.toml`**

In the `[project]` → `dependencies` list:

```toml
dependencies = [
    "agno[anthropic,os,telegram]>=2.0.0",
    "python-dotenv>=1.0.0",
    "sqlalchemy>=2.0.0",
    "PyGithub>=2.0.0",
    "pyyaml>=6.0",
]
```

- [ ] **Step 2: Install new dependencies**

```bash
uv sync
```

Expected: no errors; `PyGithub` and `PyYAML` appear in resolved packages.

- [ ] **Step 3: Verify installation**

```bash
python -c "import github; import yaml; print('ok')"
```

Expected output: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add PyGithub and pyyaml dependencies"
```

---

### Task 2: Pydantic models

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/provision.py` (models only — no tool function yet)
- Create: `tests/test_provision.py` (2 tests)

> Note: `tools/provision.py` in this task does **not** import from agno. The `@tool` decorator and its import are added in Task 3 after the conftest mock is updated.

- [ ] **Step 1: Create `tools/__init__.py`**

```python
from tools.provision import provision_platform_instance

__all__ = ["provision_platform_instance"]
```

- [ ] **Step 2: Write failing tests for manifest models**

Create `tests/test_provision.py`:

```python
import pytest


def test_manifest_build():
    from tools.provision import PlatformManifest

    manifest = PlatformManifest.build(
        name="wp2",
        domain="wasp.silvios.me",
        regions=["us-east-1", "sa-east-1"],
    )

    assert manifest.name == "wp2"
    assert manifest.spec.domain == "wasp.silvios.me"
    assert len(manifest.spec.regions) == 2
    r0 = manifest.spec.regions[0]
    assert r0.name == "us-east-1"
    assert r0.endpoint == "gateway.us-east-1.wp2.wasp.silvios.me"
    r1 = manifest.spec.regions[1]
    assert r1.endpoint == "gateway.sa-east-1.wp2.wasp.silvios.me"
    assert [s.name for s in manifest.spec.services] == [
        "auth", "discovery", "callback", "portal"
    ]


def test_manifest_yaml_output():
    import yaml
    from tools.provision import PlatformManifest

    manifest = PlatformManifest.build("wp2", "wasp.silvios.me", ["us-east-1"])
    yaml_str = yaml.dump(manifest.model_dump(), default_flow_style=False, sort_keys=False)
    data = yaml.safe_load(yaml_str)

    assert data["apiVersion"] == "wasp.silvios.me/v1alpha1"
    assert data["kind"] == "Platform"
    assert data["name"] == "wp2"
    assert data["spec"]["domain"] == "wasp.silvios.me"
    assert data["spec"]["regions"][0]["endpoint"] == "gateway.us-east-1.wp2.wasp.silvios.me"
    assert len(data["spec"]["services"]) == 4
    assert [s["name"] for s in data["spec"]["services"]] == [
        "auth", "discovery", "callback", "portal"
    ]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_provision.py -v
```

Expected: 2 FAIL — `tools.provision` does not exist yet.

- [ ] **Step 4: Create `tools/provision.py` with models only**

```python
import os

import yaml
from github import Github
from pydantic import BaseModel, Field

DEFAULT_DOMAIN = "wasp.silvios.me"
DEFAULT_REGIONS = ["us-east-1"]


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
            ServiceSpec(name=s)
            for s in ["auth", "discovery", "callback", "portal"]
        ]
    )


class PlatformManifest(BaseModel):
    apiVersion: str = "wasp.silvios.me/v1alpha1"
    kind: str = "Platform"
    name: str
    spec: PlatformSpec

    @classmethod
    def build(cls, name: str, domain: str, regions: list[str]) -> "PlatformManifest":
        return cls(
            name=name,
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_provision.py::test_manifest_build tests/test_provision.py::test_manifest_yaml_output -v
```

Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/__init__.py tools/provision.py tests/test_provision.py
git commit -m "feat(provision): add PlatformManifest Pydantic models"
```

---

### Task 3: Tool function + conftest update

**Files:**
- Modify: `tests/conftest.py` (add `agno.tools` mock + module teardown)
- Modify: `tools/provision.py` (add `@tool` import and `provision_platform_instance`)
- Modify: `tests/test_provision.py` (add 2 more tests)

- [ ] **Step 1: Find the agno `@tool` import path**

```bash
find .venv/lib -name "*.py" | xargs grep -rl "requires_confirmation" 2>/dev/null | head -5
```

Note the module path (e.g., `.venv/lib/.../agno/tools/__init__.py`). Convert to Python import path (e.g., `agno.tools`). Use it in Step 3 and Step 4 below.

If the result is empty, try:

```bash
python -c "import agno; print(agno.__file__)"
find .venv/lib -path "*/agno*" -name "*.py" | head -20
```

- [ ] **Step 2: Update `tests/conftest.py`**

Replace the entire file content with:

```python
import sys
from unittest.mock import MagicMock
import pytest

AGNO_MODULES = [
    "agno",
    "agno.agent",
    "agno.models",
    "agno.models.anthropic",
    "agno.db",
    "agno.db.sqlite",
    "agno.db.sqlite.sqlite",
    "agno.os",
    "agno.os.interfaces",
    "agno.os.interfaces.telegram",
    "agno.tools",
]


@pytest.fixture(autouse=True)
def mock_agno(monkeypatch):
    # Clear cached modules so each test gets a fresh import with current mocks.
    for mod in ("main", "tools", "tools.provision"):
        sys.modules.pop(mod, None)

    mocks = {name: MagicMock() for name in AGNO_MODULES}
    for name, mock in mocks.items():
        monkeypatch.setitem(sys.modules, name, mock)
    # Make @tool(requires_confirmation=True) a transparent no-op so
    # provision_platform_instance remains directly callable in tests.
    mocks["agno.tools"].tool = lambda **kwargs: lambda fn: fn
    # Prevent load_dotenv() from reading the real .env during tests so that
    # monkeypatch.setenv/delenv has full control over env vars.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    yield mocks

    for mod in ("main", "tools", "tools.provision"):
        sys.modules.pop(mod, None)
```

- [ ] **Step 3: Run existing tests to verify conftest change is safe**

```bash
pytest tests/test_main.py -v
```

Expected: 3 PASS.

- [ ] **Step 4: Add `@tool` import and the tool function to `tools/provision.py`**

Add the import from agno at the top of the file (use the module path found in Step 1, e.g. `agno.tools`):

```python
from agno.tools import tool
```

Append the function after the `PlatformManifest` class:

```python
@tool(requires_confirmation=True)
def provision_platform_instance(
    name: str,
    domain: str = DEFAULT_DOMAIN,
    regions: list[str] = DEFAULT_REGIONS,
    requested_by: str = "",
) -> dict:
    """
    Provisions a new Platform by committing a Crossplane manifest to
    smsilva/wasp-gitops. ArgoCD picks it up automatically.

    Returns: commit_sha, file_path, status.
    """
    pat = os.getenv("GH_PAT")
    if not pat:
        raise ValueError("GH_PAT environment variable is required")

    manifest = PlatformManifest.build(name=name, domain=domain, regions=regions)
    yaml_content = yaml.dump(manifest.model_dump(), default_flow_style=False, sort_keys=False)

    repo = Github(pat).get_repo("smsilva/wasp-gitops")
    file_path = f"infrastructure/tenants/{name}.yaml"
    commit_message = f"feat(tenants): provision {name}\n\nRequested by: {requested_by}"

    result = repo.create_file(
        path=file_path,
        message=commit_message,
        content=yaml_content,
        branch="dev",
    )

    return {
        "commit_sha": result["commit"].sha,
        "file_path": file_path,
        "status": "provisioning",
        "message": "Commit feito. ArgoCD vai sincronizar em ~1min.",
    }
```

- [ ] **Step 5: Add 2 more tests to `tests/test_provision.py`**

Append to the file:

```python
def test_provision_commits(monkeypatch):
    from unittest.mock import MagicMock
    from tools.provision import provision_platform_instance

    mock_github_cls = MagicMock()
    mock_repo = MagicMock()
    mock_commit = MagicMock()
    mock_commit.sha = "abc123def456"
    mock_github_cls.return_value.get_repo.return_value = mock_repo
    mock_repo.create_file.return_value = {"commit": mock_commit, "content": MagicMock()}

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setattr("tools.provision.Github", mock_github_cls)

    result = provision_platform_instance(
        name="wp2",
        domain="wasp.silvios.me",
        regions=["us-east-1"],
        requested_by="alice",
    )

    mock_github_cls.assert_called_once_with("fake-pat")
    mock_github_cls.return_value.get_repo.assert_called_once_with("smsilva/wasp-gitops")
    call_kwargs = mock_repo.create_file.call_args.kwargs
    assert call_kwargs["path"] == "infrastructure/tenants/wp2.yaml"
    assert call_kwargs["branch"] == "dev"
    assert "feat(tenants): provision wp2" in call_kwargs["message"]
    assert "Requested by: alice" in call_kwargs["message"]
    assert result["commit_sha"] == "abc123def456"
    assert result["file_path"] == "infrastructure/tenants/wp2.yaml"
    assert result["status"] == "provisioning"


def test_provision_missing_pat(monkeypatch):
    from unittest.mock import MagicMock
    from tools.provision import provision_platform_instance

    monkeypatch.delenv("GH_PAT", raising=False)
    mock_github_cls = MagicMock()
    monkeypatch.setattr("tools.provision.Github", mock_github_cls)

    with pytest.raises(ValueError, match="GH_PAT"):
        provision_platform_instance(name="wp2")

    mock_github_cls.assert_not_called()
```

- [ ] **Step 6: Run all provision tests**

```bash
pytest tests/test_provision.py -v
```

Expected: 4 PASS.

- [ ] **Step 7: Verify coverage for `tools/`**

```bash
pytest tests/test_provision.py --cov=tools --cov-report=term-missing
```

Expected: 100% on `tools/provision.py`. `tools/__init__.py` will be covered after Task 4 wires it into `main.py`.

- [ ] **Step 8: Commit**

```bash
git add tests/conftest.py tools/provision.py tests/test_provision.py
git commit -m "feat(provision): implement provision_platform_instance tool"
```

---

### Task 4: Wire tool into `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add tool import to `main.py`**

After the existing agno imports (around line 14), add:

```python
from tools.provision import provision_platform_instance  # noqa: E402
```

- [ ] **Step 2: Add `tools` to the `Agent(...)` call**

Change:

```python
agent = Agent(
    name="wasp-agent",
    model=Claude(id="bedrock/anthropic.claude-4-5-haiku"),
    db=SqliteDb(db_file="agent.db", session_table="agent_sessions"),
    add_history_to_context=True,
    instructions=INSTRUCTIONS,
)
```

To:

```python
agent = Agent(
    name="wasp-agent",
    model=Claude(id="bedrock/anthropic.claude-4-5-haiku"),
    db=SqliteDb(db_file="agent.db", session_table="agent_sessions"),
    add_history_to_context=True,
    instructions=INSTRUCTIONS,
    tools=[provision_platform_instance],
)
```

- [ ] **Step 3: Run all tests with full coverage**

```bash
pytest --cov --cov-report=term-missing -v
```

Expected: 7 PASS, 100% coverage across `main.py`, `tools/__init__.py`, and `tools/provision.py`.

- [ ] **Step 4: Run ruff**

```bash
ruff check .
```

Expected: no errors. If there are E402 errors on the new import, add `# noqa: E402` — this is an intentional violation (env vars must load before module-level imports).

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat(agent): register provision_platform_instance tool"
```
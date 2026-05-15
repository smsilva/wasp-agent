# Platform Provisioning — Design

**Date:** 2026-05-15
**Scope:** Fase 1 (extração) + Fase 2 (commit GitOps). Watcher assíncrono fica para o próximo ciclo.

---

## Objective

Add a `provision_platform_instance` tool to the existing Agno agent so users can request a new Platform instance via natural language on Telegram. The agent extracts parameters, shows a confirmation summary, and commits a Crossplane manifest to `smsilva/wasp-gitops` on branch `dev`. ArgoCD picks it up automatically.

---

## Architecture

No changes to the Agent core or AgentOS. Only additions:

```
wasp-agent/
├── main.py                        # imports and registers the new tool
├── tools/
│   ├── __init__.py
│   └── provision.py               # PlatformManifest models + tool
├── tests/
│   ├── conftest.py                # existing mocks + PyGithub mock
│   ├── test_main.py               # existing tests (unchanged)
│   └── test_provision.py          # 4 new tests
```

---

## Manifest Model

```
apiVersion: wasp.silvios.me/v1alpha1
kind: Platform
name: <name>
spec:
  domain: <domain>
  regions:
    - name: <aws-region>
      endpoint: gateway.<aws-region>.<name>.<domain>
  services:
    - name: auth
    - name: discovery
    - name: callback
    - name: portal
```

Endpoint is derived deterministically: `gateway.{aws-region}.{name}.{domain}`. No field is unknown at commit time.

Services are fixed for all Platform instances.

### Pydantic Models

```python
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

---

## Tool

```python
DEFAULT_DOMAIN = "wasp.silvios.me"
DEFAULT_REGIONS = ["us-east-1"]

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

    Returns: commit_sha, file_path.
    """
```

`requires_confirmation=True` causes the agent to display extracted parameters and ask the user to confirm before committing.

**Commit details:**
- Repo: `smsilva/wasp-gitops`
- Branch: `dev`
- Path: `infrastructure/tenants/{name}.yaml`
- Message: `feat(tenants): provision {name}\n\nRequested by: {requested_by}`

**`GH_PAT` guard:** if `os.getenv("GH_PAT")` is absent, the tool raises `ValueError` with a clear message before touching GitHub.

### Return value

```python
{
    "commit_sha": "a1b2c3d...",
    "file_path": "infrastructure/tenants/wp2.yaml",
    "status": "provisioning",
    "message": "Commit feito. ArgoCD vai sincronizar em ~1min.",
}
```

---

## Data Flow

```
User: "cria plataforma wp2 nas regiões us-east-1 e sa-east-1"
    ↓
Agent extracts: name="wp2", domain="wasp.silvios.me", regions=["us-east-1","sa-east-1"]
    ↓
requires_confirmation=True → agent shows parameters + derived endpoints + path
    ↓
User confirms
    ↓
PlatformManifest.build(...) → yaml.dump() → repo.create_file(...)
    ↓
Return: commit_sha, file_path, "ArgoCD sincroniza em ~1min"
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `GH_PAT` | Fine-grained PAT — `smsilva/wasp-gitops`, `Contents: write`, branch `dev` |

`DEFAULT_DOMAIN` and `DEFAULT_REGIONS` are constants in `tools/provision.py`, not env vars.

---

## Dependencies

Add to `pyproject.toml`:

```toml
"PyGithub>=2.0.0",
"pyyaml>=6.0",
```

---

## Testing

Coverage threshold: 100%.

| Test | What it verifies |
|---|---|
| `test_manifest_build` | Endpoint derived correctly: `gateway.{region}.{name}.{domain}` |
| `test_manifest_yaml_output` | Serialized YAML has correct `apiVersion`, `kind`, `name`, `spec` |
| `test_provision_commits` | Mock PyGithub — correct path `infrastructure/tenants/{name}.yaml` and commit content |
| `test_provision_missing_pat` | `ValueError` raised when `GH_PAT` is absent, before any GitHub call |

---

## Out of Scope

- Async watcher + proactive Telegram notification (next cycle)
- Duplicate detection (tool returns GitHub's 422 as an exception for now)
- GitHub App (PAT fine-grained for MVP)
- PR flow (direct commit to `dev` branch)

---

## Next Cycle

Add watcher: `asyncio.create_task` in-process polls Kubernetes until the Platform resource reaches `Ready: True`, then sends a proactive Telegram message with the access URLs.

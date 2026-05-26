# Refatoração de `provision_platform_instance` + nova tool `list_platform_instances`

**Date:** 2026-05-25  
**Status:** Draft  
**Scope:** `wasp/provision.py`, `wasp/watcher.py`, `tests/test_complexity.py`, novos arquivos `wasp/auth_guard.py`, `wasp/gitops_committer.py`, `wasp/platform_cluster.py`, `main.py`.

## Contexto

`provision_platform_instance` em `wasp/provision.py` tem cyclomatic complexity (CC) = 15, acima do limite alvo do projeto. O backlog do `HANDOFF.md` registra a redução para CC ≤ 10. Além disso, o mesmo backlog tem "Operações além de criar — update, delete, list de tenants". Esta refatoração resolve a redução de CC e entrega a operação `list` no mesmo ciclo, evitando duplicação de scaffolding.

## Problema

Três problemas convergem:

1. **CC alta** em uma única função de ~100 linhas que mistura quatro responsabilidades: autorização, build de manifesto, commit no Git, spawn do watcher.
2. **Sem operação `list`** — usuário não consegue perguntar "quais tenants existem?" via Telegram/CLI.
3. **Acoplamento que dificulta novos recursos** — manifesto, path do arquivo e cliente Git estão entrelaçados, impedindo reuso da camada de GitOps para recursos futuros (User, Database, etc., conforme intenção do operador).

## Direção

Decomposição em classes com responsabilidade única + orquestradores. Cada classe testável em isolamento.

### Classes novas

#### `AuthorizationGuard` (`wasp/auth_guard.py`)

Encapsula a checagem de auth: combina `auth.is_authorized()`, `TRUSTED_CHANNELS`, telemetria de auth denied, e span attribute setting.

```python
class AuthorizationGuard:
    def check(
        self, channel: str | None, chat_id: str | None, span
    ) -> tuple[str | None, dict | None]:
        """
        Retorna (user_id, error_response).
        - error_response is None  → autorizado, prosseguir.
        - error_response is dict  → bloquear, retornar esse dict ao caller.
        """
```

Lógica interna (mesma da função atual):
- Sem `channel` → `(None, None)` (sem identidade, mas sem bloqueio explícito; comportamento atual).
- `channel in TRUSTED_CHANNELS` → `("local-operator", None)`.
- Outros → consulta `auth.is_authorized()`. Se `None`, registra `auth_denied` e devolve `(None, {"status": "unauthorized", "message": "Acesso negado."})`.

Span attributes setados: `auth.channel`, `user.id` (quando resolvido).

#### `GitOpsCommitter` (`wasp/gitops_committer.py`)

Wrappa `PyGithubClient`. Operação genérica de commit — não conhece o domínio "platform".

```python
class GitOpsCommitter:
    def __init__(self, client: GitClient):
        self._client = client

    @classmethod
    def from_env(cls) -> "GitOpsCommitter":
        pat = os.getenv("GH_PAT")
        if not pat:
            raise ValueError("GH_PAT not set")
        return cls(PyGithubClient(
            pat=pat,
            repo=os.getenv("GITOPS_REPO", "smsilva/wasp-gitops"),
            base_url=os.getenv("GITHUB_BASE_URL", "https://api.github.com"),
        ))

    def commit(
        self, file_path: str, yaml_content: str, commit_message: str
    ) -> dict | None:
        """
        Commita o arquivo no branch `dev`. Retorna:
        - None                                     → sucesso.
        - {"status": "already_provisioning", ...}  → arquivo já existe (FileAlreadyExistsError).
        """
```

Genérico para reusar com futuros recursos (`UserManifest`, `DatabaseManifest`).

#### `PlatformClusterReader` (`wasp/platform_cluster.py`)

Lê Platform CRs do K8s cluster. Hardcoded para o CRD `Platform` por enquanto — generalizar quando aparecer segundo CR.

```python
class PlatformClusterReader:
    def __init__(self, api: client.CustomObjectsApi):
        self._api = api

    @classmethod
    def from_env(cls) -> "PlatformClusterReader":
        return cls(load_kube_config_auto())

    def list_with_status(self) -> list[dict]:
        """
        Retorna [{"name": str, "status": "Ready" | "Pending" | "Unknown"}, ...].
        - Ready    → condition Ready=True.
        - Pending  → condition Ready=False (reconciliando).
        - Unknown  → sem condition Ready (ArgoCD não sincou ainda).
        """
```

Reusa `load_kube_config_auto()` existente em `wasp/watcher.py`.

#### `PlatformWatcherSpawner` (`wasp/watcher.py`)

Movido pra dentro de `wasp/watcher.py` porque acoplado a `watch_platform`. Encapsula seleção do notifier + spawn da thread.

```python
class PlatformWatcherSpawner:
    def spawn(
        self,
        name: str,
        chat_id: str | None,
        channel: str | None,
        parent_span_ctx,
    ) -> bool:
        """
        Spawna thread daemon rodando watch_platform. Retorna:
        - True   → spawnou.
        - False  → sem chat_id ou notifier indisponível.
        """
```

`_select_notifier` é movida para `wasp/watcher.py` (mesmo módulo que `PlatformWatcherSpawner`) para evitar import circular `watcher → provision`. Testes que patcheiam `wasp.provision._select_notifier` (ex.: `tests/e2e/conftest.py`, ver CLAUDE.md §19) precisam atualizar o target para `wasp.watcher._select_notifier`.

#### `PlatformProvisioner` (`wasp/provision.py`)

Orquestrador da operação de provisionamento. Composto por `AuthorizationGuard` + `GitOpsCommitter` + `PlatformWatcherSpawner`.

```python
class PlatformProvisioner:
    def __init__(
        self,
        guard: AuthorizationGuard,
        committer: GitOpsCommitter,
        watcher_spawner: PlatformWatcherSpawner,
    ): ...

    @classmethod
    def from_env(cls) -> "PlatformProvisioner":
        return cls(
            guard=AuthorizationGuard(),
            committer=GitOpsCommitter.from_env(),
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
        ...
```

Fluxo de `provision()`:

```
1. channel, chat_id = extract_channel/chat_id(run_context)
2. user_id, err = guard.check(channel, chat_id, span)
   if err: return err
3. manifest = PlatformManifest.build(name, domain, regions)
4. yaml_content = yaml.safe_dump(manifest.model_dump(), ...)
5. err = committer.commit(
     file_path=f"infrastructure/tenants/{name}.yaml",
     yaml_content=yaml_content,
     commit_message=...,
   )
   if err: return err  # already_provisioning
6. span.set_attribute("platform.name", name)
7. telemetry.provisioning_counter.add(1, {"outcome": "started"})
8. watcher_spawner.spawn(name, chat_id, channel, span.get_span_context())
9. return {"status": "provisioning", "message": ...}
```

Try/except externo (`except Exception`) permanece no orquestrador.

#### `PlatformInventory` (`wasp/provision.py`)

Orquestrador da operação de listagem. Composto por `AuthorizationGuard` + `PlatformClusterReader`.

```python
class PlatformInventory:
    def __init__(
        self,
        guard: AuthorizationGuard,
        reader: PlatformClusterReader,
    ): ...

    @classmethod
    def from_env(cls) -> "PlatformInventory":
        return cls(
            guard=AuthorizationGuard(),
            reader=PlatformClusterReader.from_env(),
        )

    def list(self, run_context) -> dict:
        ...
```

Fluxo de `list()`:

```
1. channel, chat_id = extract_channel/chat_id(run_context)
2. user_id, err = guard.check(channel, chat_id, span)
   if err: return err
3. tenants = reader.list_with_status()
4. return {"status": "ok", "tenants": tenants}
```

Try/except externo (`except Exception`) permanece no orquestrador.

### Entry points (`wasp/provision.py`)

```python
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


@tool
@telemetry.instrument("list_platform_instances")
def list_platform_instances(run_context=None) -> dict:
    """
    Lists all provisioned platform instances and their cluster status.
    Read-only — safe to call without confirmation.
    """
    return PlatformInventory.from_env().list(run_context=run_context)
```

### Registro em `main.py`

```python
from wasp import auth, list_platform_instances, provision_platform_instance  # noqa: E402

agent = Agent(
    ...
    tools=[provision_platform_instance, list_platform_instances],
    ...
)
```

System prompt ganha uma linha:

> `list_platform_instances` is read-only — safe to call without explicit user confirmation.

## Modelo de dados

Sem mudanças. Reusa:
- `PlatformManifest`, `PlatformSpec`, `RegionSpec`, `ServiceSpec`, `MetadataSpec` (pydantic models existentes em `wasp/provision.py`).
- Tabelas `auth_users`, `auth_identities` via `wasp/auth.py`.
- Platform CRD existente (`wasp.silvios.me/v1alpha1`).

## Retorno das tools

### `provision_platform_instance` (sem mudança)

```json
{"status": "provisioning",  "message": "Request accepted. ..."}
{"status": "already_provisioning", "message": "Tenant 'X' is already being provisioned."}
{"status": "unauthorized", "message": "Acesso negado."}
{"status": "error", "message": "Provisioning failed. Please try again later."}
```

### `list_platform_instances` (nova)

```json
{
  "status": "ok",
  "tenants": [
    {"name": "acme",   "status": "Ready"},
    {"name": "globex", "status": "Pending"},
    {"name": "init",   "status": "Unknown"}
  ]
}
{"status": "unauthorized", "message": "Acesso negado."}
{"status": "error", "message": "List failed. Please try again later."}
```

Status semantics:
- `Ready` — Platform CR tem `Ready=True`.
- `Pending` — Platform CR tem `Ready=False` (ArgoCD sincou, Crossplane reconciliando).
- `Unknown` — Platform CR sem condition `Ready` (ArgoCD ainda não sincou).

## Tratamento de erros

`provision()` e `list()` envelopam o fluxo num try/except `Exception` único, devolvendo `{"status": "error", "message": "..."}` + log `log.exception(...)` + telemetria.

`GitOpsCommitter.from_env()` levanta `ValueError` se `GH_PAT` ausente — capturado pelo try/except do orquestrador. (Falha clara em config ausente é item separado no backlog.)

## Testes

**Unit tests** (cada classe isolada com mocks):

- `tests/test_auth_guard.py` — TRUSTED_CHANNELS, unknown identity, sem channel, sem chat_id.
- `tests/test_gitops_committer.py` — commit ok, FileAlreadyExistsError → dict, env var ausente → ValueError.
- `tests/test_platform_cluster.py` — list vazio, Platform com Ready=True, Ready=False, sem condition.
- `tests/test_watcher.py` — adicionar testes para `PlatformWatcherSpawner.spawn()` (com/sem chat_id, com/sem notifier).
- `tests/test_provision.py` — `PlatformProvisioner.provision()` com mocks; `PlatformInventory.list()` com mocks.

**E2E** (`tests/e2e/`):

- Manter `test_provision_e2e` existente — sem regressão.
- Adicionar `test_list_e2e` — após provisionar 2 tenants, `list_platform_instances` retorna ambos com `status="Pending"` ou `"Ready"` dependendo do timing.

**Cobertura:** manter 100% (limite atual do projeto).

**Cyclomatic complexity:** após refatoração, atualizar `MAX_COMPLEXITY = 10` em `tests/test_complexity.py`. Verificar que todas as funções/métodos ficam ≤ 10.

## Pontos abertos

Nenhum bloqueio para implementação.

## Decisões fechadas (conversa de 2026-05-25)

- **Decomposição em classes** com nomes significativos (preferência do operador), não funções privadas.
- **`PlatformInventory`** como nome do orquestrador da listagem (vs. `PlatformLister`).
- **`list_platform_instances` retorna status real do K8s** (opção c), não só nomes do GitOps repo.
- **`GitOpsCommitter.commit()` genérico** (recebe file_path + yaml_content) para reusar em futuros recursos.
- **`PlatformClusterReader` platform-specific por enquanto** — generalizar quando aparecer segundo CR.
- **`PlatformWatcherSpawner` em `wasp/watcher.py`** porque acoplado a `watch_platform`.
- **Manter `provision_platform_instance` com assinatura idêntica** — zero breaking changes na tool.

## Próximo passo

Criar plano de execução em `docs/sdlc/03-execution/2026-05-25-platform-provision-refactor-plan.md`.

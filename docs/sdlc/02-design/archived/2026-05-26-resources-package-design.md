# Resources Package Design

**Date:** 2026-05-26  
**Status:** Approved  
**Scope:** `wasp/provision.py`, `wasp/platform_cluster.py`, `wasp/watcher.py` (imports apenas), `wasp/clients/k8s/` (novo), `wasp/resources/` (novo)

## Problem

`wasp/provision.py` mistura três responsabilidades: modelos Pydantic do CRD Platform (`PlatformManifest`, `PlatformSpec`, `RegionSpec`, `ServiceSpec`, `MetadataSpec`), classes operacionais (`PlatformProvisioner`, `PlatformInventory`) e os `@tool` que o agente expõe. O próximo CRD planejado — `Cluster` — vai duplicar esse padrão: manifest Pydantic, provisioner que faz commit no GitOps, inventory que lê do k8s.

`wasp/platform_cluster.py` mistura duas coisas: chamar a API do k8s com `(group, version, plural)` hardcoded e transformar o resultado em `[{name, status}]`. A primeira é genérica; a segunda é específica de Platform.

Sem reorganização, adicionar `Cluster` duplica código e amarra mais classes ao nome "Platform".

## Solution

Introduzir dois pacotes:

- `wasp/resources/` — base comum + um subpacote por CRD (`platform/`, futuramente `cluster/`).
- `wasp/clients/k8s/` — cliente genérico da API do Kubernetes, seguindo o padrão `wasp/clients/<external-service>/` já estabelecido para Telegram/local.

`wasp/provision.py` vira fachada plana de `@tool`s, sem lógica.

`wasp/platform_cluster.py` é removido; sua lógica genérica vira `KubernetesResourceReader`, sua lógica específica vira parte do `PlatformInventory`.

## Layout

```
wasp/resources/
  __init__.py              ← re-exporta ResourceManifest, MetadataSpec
  base.py                  ← ResourceManifest, MetadataSpec, WASP_API_VERSION
  platform/
    __init__.py            ← re-exporta PlatformManifest, PlatformProvisioner, PlatformInventory
    manifest.py            ← PlatformManifest, PlatformSpec, RegionSpec, ServiceSpec,
                              PLATFORM_GROUP, PLATFORM_VERSION, PLATFORM_PLURAL
    provisioner.py         ← PlatformProvisioner + DEFAULT_DOMAIN, DEFAULT_REGIONS
    inventory.py           ← PlatformInventory + _status_from_conditions

wasp/clients/k8s/
  __init__.py              ← load_kube_config_auto + re-export de KubernetesResourceReader
  reader.py                ← KubernetesResourceReader

wasp/provision.py          ← apenas dois @tool (list_platform_instances, provision_platform_instance)
wasp/platform_cluster.py   ← REMOVIDO
wasp/watcher.py            ← passa a importar PLATFORM_GROUP/VERSION/PLURAL e
                              load_kube_config_auto dos novos locais
```

## Base class

```python
# wasp/resources/base.py
from pydantic import BaseModel

WASP_API_VERSION = "wasp.silvios.me/v1alpha1"

class MetadataSpec(BaseModel):
    name: str

class ResourceManifest(BaseModel):
    apiVersion: str = WASP_API_VERSION
    metadata: MetadataSpec
    # subclasses definem `kind: str = "X"` e `spec: SubclassSpec`
```

Subclasse Platform:

```python
# wasp/resources/platform/manifest.py
class PlatformManifest(ResourceManifest):
    kind: str = "Platform"
    spec: PlatformSpec

    @classmethod
    def build(cls, name: str, domain: str, regions: list[str]) -> "PlatformManifest":
        # mantém a implementação atual de PlatformManifest.build
        ...
```

Quando `Cluster` chegar: `wasp/resources/cluster/manifest.py` cria `ClusterManifest(ResourceManifest)` com `kind = "Cluster"` e seu próprio `ClusterSpec`. Nenhuma mudança na base.

## Generic k8s reader

```python
# wasp/clients/k8s/__init__.py
from kubernetes import client, config


def load_kube_config_auto() -> "client.CustomObjectsApi":
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CustomObjectsApi()


from wasp.clients.k8s.reader import KubernetesResourceReader as KubernetesResourceReader  # noqa: E402
```

```python
# wasp/clients/k8s/reader.py
from kubernetes.client import CustomObjectsApi
from wasp.clients.k8s import load_kube_config_auto


class KubernetesResourceReader:
    def __init__(self, api: CustomObjectsApi):
        self._api = api

    @classmethod
    def from_env(cls) -> "KubernetesResourceReader":
        return cls(api=load_kube_config_auto())

    def search_for_instance_of(self, group: str, version: str, plural: str) -> list[dict]:
        result = self._api.list_cluster_custom_object(
            group=group, version=version, plural=plural
        )
        return result.get("items", [])
```

`load_kube_config_auto` move de `wasp/watcher.py` para `wasp/clients/k8s/__init__.py`. A definição precede o `from .reader import …` para que o `reader.py` consiga importá-la sem ciclo. Watcher passa a fazer `from wasp.clients.k8s import load_kube_config_auto`.

## PlatformInventory após o refactor

```python
# wasp/resources/platform/inventory.py
from wasp.clients.k8s import KubernetesResourceReader
from wasp.resources.platform.manifest import (
    PLATFORM_GROUP, PLATFORM_PLURAL, PLATFORM_VERSION,
)

class PlatformInventory:
    def __init__(self, guard, reader: KubernetesResourceReader):
        self._guard = guard
        self._reader = reader

    @classmethod
    def from_env(cls) -> "PlatformInventory":
        return cls(
            guard=AuthorizationGuard(),
            reader=KubernetesResourceReader.from_env(),
        )

    def list(self, run_context) -> dict:
        # ... auth check inalterado
        items = self._reader.search_for_instance_of(
            PLATFORM_GROUP, PLATFORM_VERSION, PLATFORM_PLURAL
        )
        tenants = [
            {"name": i["metadata"]["name"], "status": _status_from_conditions(i)}
            for i in items
        ]
        return {"status": "ok", "tenants": tenants}
```

A transformação `_status_from_conditions` migra junto.

## provision.py após o refactor

```python
# wasp/provision.py
from agno.tools import tool
import wasp.telemetry as telemetry
from wasp.resources.platform import PlatformInventory, PlatformProvisioner
from wasp.resources.platform.provisioner import DEFAULT_DOMAIN, DEFAULT_REGIONS

@tool
@telemetry.instrument("list_platform_instances")
def list_platform_instances(run_context=None) -> dict:
    """..."""
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
    """..."""
    if regions is None:
        regions = list(DEFAULT_REGIONS)
    return PlatformProvisioner.from_env().provision(
        name=name, domain=domain, regions=regions,
        requested_by=requested_by, run_context=run_context,
    )
```

Quando `Cluster` chegar, adiciona-se aqui `@tool provision_cluster_instance` e `@tool list_cluster_instances`, importando de `wasp.resources.cluster`.

## Default `requested_by`

Hoje, se o LLM chamar `provision_platform_instance` sem `requested_by`, o commit message termina com `"Requested by: "` (vazio). Como o `AuthorizationGuard` já resolve `user_id`, o `PlatformProvisioner` usa esse valor como fallback:

```python
# wasp/resources/platform/provisioner.py
user_id, err = self._guard.check(channel, chat_id, span)
if err is not None:
    return err
if not requested_by:
    requested_by = user_id or "unknown"
```

Resultado:
- Canal local: `Requested by: local-operator`
- Telegram autenticado: `Requested by: <user_id resolvido pela auth>`
- Sem `run_context` (cenário improvável): `Requested by: unknown`

Cobertura de teste: adicionar caso em `tests/test_provision.py` que chama `provision_platform_instance` com `requested_by=""` e verifica que o commit message recebe o `user_id` no lugar.

## Out of scope

- Generalização do `PlatformWatcherSpawner` / `watch_platform` para múltiplos CRDs. Watcher é assíncrono e tem fronteira diferente (notificação, polling). Refatorar quando Cluster precisar de watcher.
- Generalização do `GitOpsCommitter` ou `git_client.py` para múltiplos backends (Bitbucket, GitLab). `GitClient` Protocol já existe; suficiente por enquanto.
- Movimentação de `wasp/git_client.py` ou `wasp/gitops_committer.py` para `wasp/clients/`. Pergunta aberta em `docs/sdlc/01-exploration/clients-package-pattern.md`; decisão fica para quando houver demanda concreta.

## Migration order

Para manter `make test` verde a cada passo:

1. Criar `wasp/resources/__init__.py`, `wasp/resources/base.py`, `wasp/resources/platform/__init__.py`, `wasp/resources/platform/manifest.py`. Move `PlatformManifest`, specs e constantes `PLATFORM_GROUP/VERSION/PLURAL`. `wasp/watcher.py` passa a importar daqui.
2. Criar `wasp/clients/k8s/{__init__,reader}.py`. Move `load_kube_config_auto` de `watcher.py` para `__init__.py`. Watcher importa de `wasp.clients.k8s`. Atualiza `tests/test_watcher.py` (8 patches em `load_kube_config_auto` continuam funcionando porque o watcher rebind o nome via `from … import …`).
3. Criar `wasp/resources/platform/inventory.py` com `PlatformInventory` + `_status_from_conditions`, agora usando `KubernetesResourceReader`.
4. Criar `wasp/resources/platform/provisioner.py` com `PlatformProvisioner` + `DEFAULT_DOMAIN/REGIONS`.
5. Atualizar `wasp/provision.py` para conter apenas os dois `@tool`.
6. Remover `wasp/platform_cluster.py`.
7. Atualizar imports nos testes; renomear `tests/test_platform_cluster.py` → `tests/test_k8s_reader.py`; adicionar `tests/test_platform_inventory.py` para a transformação de status.
8. Atualizar `tests/conftest.py` — lista de `sys.modules.pop`: adicionar `wasp.resources`, `wasp.resources.base`, `wasp.resources.platform`, `wasp.resources.platform.manifest`, `wasp.resources.platform.provisioner`, `wasp.resources.platform.inventory`, `wasp.clients.k8s`, `wasp.clients.k8s.reader`; remover `wasp.platform_cluster`.
9. Validação final: `make format && make test && make e2e-with-debug`.

## Files changed

| File | Change |
|---|---|
| `wasp/resources/__init__.py` | novo — re-exporta `ResourceManifest`, `MetadataSpec` |
| `wasp/resources/base.py` | novo — `ResourceManifest`, `MetadataSpec`, `WASP_API_VERSION` |
| `wasp/resources/platform/__init__.py` | novo — re-exporta classes públicas do CRD Platform |
| `wasp/resources/platform/manifest.py` | novo — `PlatformManifest`, `PlatformSpec`, `RegionSpec`, `ServiceSpec`, constantes `PLATFORM_*` |
| `wasp/resources/platform/provisioner.py` | novo — `PlatformProvisioner`, `DEFAULT_DOMAIN`, `DEFAULT_REGIONS` |
| `wasp/resources/platform/inventory.py` | novo — `PlatformInventory`, `_status_from_conditions` |
| `wasp/clients/k8s/__init__.py` | novo — `load_kube_config_auto` + re-exporta `KubernetesResourceReader` |
| `wasp/clients/k8s/reader.py` | novo — `KubernetesResourceReader` |
| `wasp/provision.py` | reduz a ~25 linhas: dois `@tool` + imports |
| `wasp/platform_cluster.py` | removido |
| `wasp/watcher.py` | imports apenas: `PLATFORM_GROUP/VERSION/PLURAL` e `load_kube_config_auto` dos novos locais |
| `tests/test_provision.py` | imports atualizados |
| `tests/test_platform_cluster.py` | renomeado para `tests/test_k8s_reader.py`; testa reader genérico |
| `tests/test_platform_inventory.py` | novo — cobre `_status_from_conditions` e o fluxo de `PlatformInventory.list` |
| `tests/test_watcher.py` | imports atualizados se necessário |
| `tests/conftest.py` | lista `sys.modules.pop` atualizada |
| `CLAUDE.md` | seção "Packages" ganha referência ao padrão `wasp/resources/<crd>/` |

## Testing

- `tests/test_provision.py` continua cobrindo `PlatformManifest.build` e `provision_platform_instance` (agora via fachada).
- `tests/test_k8s_reader.py` cobre `KubernetesResourceReader.search_for_instance_of` com mock da `CustomObjectsApi`.
- `tests/test_platform_inventory.py` cobre `_status_from_conditions` (Ready/Pending/Unknown) e o fluxo `list` com `KubernetesResourceReader` mockado.
- Cobertura 100% mantida (`pytest --cov`).
- Validação final inclui `make e2e-with-debug` (não pular — captura bugs de integração que os mocks escondem).
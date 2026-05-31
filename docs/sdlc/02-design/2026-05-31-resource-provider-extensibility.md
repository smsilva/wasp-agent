# Resource Provider Extensibility (v1)

**Date:** 2026-05-31  
**Status:** Approved  
**Scope:** `wasp/resources/protocol.py` (novo), `wasp/resources/registry.py` (novo), `wasp/resources/platform/provider.py` (novo), `wasp/agent.py`  
**Brief:** `docs/sdlc/01-exploration/wasp-agent-extensibility-brief.md`

**Revisão 2026-05-31:** o discovery deixou de usar `importlib.metadata.entry_points`. O wasp-agent roda como árvore de fontes (sem `[build-system]` no `pyproject.toml`); não é um pacote instalado, então não há metadata e `entry_points()` retorna sempre `[]`. Decidiu-se **não** torná-lo um pacote instalável. O mecanismo passou a ser uma **lista de registro in-tree** (`PROVIDERS` em `registry.py`), resolvida via `importlib.import_module`, que funciona na árvore de fontes em todo lugar (local/test/e2e/Docker). Trade-off: um plugin externo (polirepo) futuro precisaria de outro mecanismo de registro — aceitável, está fora de escopo no v1.

## Problem

Adicionar um novo Custom Resource ao wasp-agent hoje exige editar o core: as `@tool` vivem em `wasp/provision.py` e são listadas nominalmente em `wasp/agent.py` (`tools=[provision_platform_instance, list_platform_instances]`). O próximo recurso (`Cluster`, já no backlog) duplicaria esse acoplamento.

Queremos adicionar recursos **sem modificar o core**, na leitura **in-tree**: criar `wasp/resources/<x>/` e registrar o provider, sem tocar em `agent.py` nem `provision.py`.

## Decision

Confirmamos a hipótese da seção 4 do brief com um ajuste de escopo: **(1) e (3) são camadas complementares, mas o v1 entrega apenas a camada (1)**.

- **(1) ResourceProvider** define o contrato interno — como o core enxerga um recurso, independente da origem.
- **(3) Loaders de CRD** (filesystem/git/cluster) ficam para v2+. A abstração `Loader` **não** é criada agora; `ResourceRegistry.discover()` fala direto com o mecanismo de plugin discovery do Python. Extrair `Loader` quando o 2º loader existir (YAGNI até lá).

Escopo escolhido: **opção A (mínima)** — contrato + registry + discovery in-tree + Platform migrado. Registro: **lista in-tree** (`PROVIDERS` em `registry.py`), não entry points de packaging. O projeto não é um pacote instalável (sem `[build-system]`), então `importlib.metadata.entry_points` não enxergaria nada; a lista in-tree resolvida via `importlib.import_module` funciona direto na árvore de fontes.

## Contract

Protocol fino, structural typing (mesmo padrão de `wasp/auth/protocol.py`):

```python
# wasp/resources/protocol.py
from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class ResourceProvider(Protocol):
    name: str                          # "platform" — logging e futura resolução de conflito
    def tools(self) -> list[Callable]: ...   # funções @tool do agno (N por recurso)
```

Decisões de forma:

- **`tools()` é método, não atributo.** Permite ao provider instanciar/configurar tools no momento da chamada (ex.: tools que dependem de env). Um atributo-lista seria avaliado no import e engessaria isso.
- **`name` permanece no Protocol** mesmo sem conflito no v1: serve para logging (`"discovered N resource providers: [...]"`) e é o gancho natural para resolução de conflito quando os loaders de CRD entrarem. Custo zero agora.
- **Metadados para o LLM não são reinventados.** Continuam sendo a docstring + type hints das funções `@tool`. Zero duplicação, zero risco de dessincronizar.

## Registry

```python
# wasp/resources/registry.py
PROVIDERS = [
    "wasp.resources.platform.provider:PlatformProvider",
]


class ResourceRegistry:
    def __init__(self, providers: list[ResourceProvider]):
        self._providers = providers

    @classmethod
    def discover(cls) -> "ResourceRegistry":
        # resolve cada path "modulo:Classe" da lista PROVIDERS via importlib.import_module
        # instancia cada classe ResourceProvider aqui
        # loga em INFO: "discovered N resource providers: [platform, ...]"
        ...

    def all_tools(self) -> list[Callable]:
        # agrega provider.tools() de todos; flat list para o Agent
        ...
```

Registro = adicionar um path `"modulo:Classe"` à lista `PROVIDERS`. É o análogo in-tree do que seria uma linha de entry point no `pyproject.toml`, mas sem exigir que o projeto vire pacote instalável. Adicionar um recurso = nova classe provider + uma linha em `PROVIDERS`, sem tocar `agent.py`/`provision.py`.

Nome `discover()` escolhido deliberadamente para descrever a **intenção** (descobrir os providers registrados) sem vazar o **mecanismo**.

## Platform como provider

As funções `@tool` **não mudam**. O provider é um wrapper fino que as agrupa:

```python
# wasp/resources/platform/provider.py
from collections.abc import Callable

from wasp.provision import list_platform_instances, provision_platform_instance


class PlatformProvider:
    name = "platform"

    def tools(self) -> list[Callable]:
        return [provision_platform_instance, list_platform_instances]
```

Registro in-tree na lista `PROVIDERS` de `registry.py` — o próprio wasp-agent declara seu provider por path:

```python
# wasp/resources/registry.py
PROVIDERS = [
    "wasp.resources.platform.provider:PlatformProvider",
]
```

**Import circular:** `provider.py` importa de `provision.py`, que importa de `wasp.resources.platform`. Para evitar ciclo, `provider.py` é **módulo folha — não reexportado** em `wasp/resources/platform/__init__.py`. A lista `PROVIDERS` referencia o provider por **string** (resolvida tarde, no `discover()`), então não há import no topo de `registry.py`; o registry só o toca via discovery.

## agent.py

```python
# antes
from wasp import list_platform_instances, provision_platform_instance
...
tools=[provision_platform_instance, list_platform_instances]

# depois
from wasp.resources.registry import ResourceRegistry
...
tools=ResourceRegistry.discover().all_tools()
```

Esta é a fatia do walk-skeleton: o `agent.py` deixa de listar tools à mão e passa a montá-las a partir do registry.

## Error handling

- **Nenhum provider descoberto** → `Agent` sem tools. Só ocorreria com `PROVIDERS` vazia (o `platform` é declarado in-tree). O log INFO de contagem torna isso visível no startup.
- **Path de provider que falha ao resolver** (módulo com erro de import ou classe inexistente) → deixar **propagar** (fail-fast no startup, alinhado com `GitOpsCommitter.probe()`). Provider quebrado é erro de deploy, não algo a engolir.
- **Conflito de nomes** → fora de escopo no v1 (provider único). `name` fica como gancho.

## Deployment / runtime

O agente roda numa container image. No v1, providers são descobertos via plugin discovery **no boot**. Logo, adicionar um recurso = nova imagem + `kubectl rollout restart`.

Isso é uma **decisão consciente, não limitação**: corresponde ao trade-off "estático, com redeploy" que o brief marca como aceitável. O custo de rollout restart é tolerável nesta versão se destrava a adição de novos recursos. Descoberta dinâmica sem restart é justamente a motivação dos loaders de CRD em v2+.

## File structure

```
wasp/resources/
  protocol.py          ← novo: ResourceProvider Protocol
  registry.py          ← novo: PROVIDERS + ResourceRegistry.discover() + all_tools()
  base.py              ← intacto
  platform/
    provider.py        ← novo: PlatformProvider (folha, não reexportado)
    manifest.py        ← intacto
    provisioner.py     ← intacto
    inventory.py       ← intacto
wasp/agent.py          ← tools=ResourceRegistry.discover().all_tools()
```

`wasp/provision.py` permanece a fachada de `@tool` (logic-free, como já é). `GitOpsCommitter` permanece o helper de commit compartilhado — requisito de reuso da seção 5 do brief, já satisfeito.

## Testing

100% de cobertura mantida (`pytest --cov`).

- `tests/test_registry.py` (novo) — `discover()` mockando `registry.PROVIDERS`/`registry._load`; `_load()` resolvendo um path real; `all_tools()` agregando múltiplos providers fake; casos: lista vazia, provider com N tools.
- `tests/test_platform_provider.py` (novo, pequeno) — `PlatformProvider.name == "platform"` e `tools()` retorna as duas funções esperadas.
- `tests/test_provision.py` — intacto (as `@tool` não mudaram).
- Teste de montagem do agente — ajustado para a nova montagem via registry.
- `tests/conftest.py` — novos módulos (`wasp.resources.protocol`, `wasp.resources.registry`, `wasp.resources.platform.provider`) adicionados à lista de `sys.modules.pop`.
- **e2e** (`make e2e-with-debug`) — exercita `discover()` → tools no agente real, resolvendo a `PROVIDERS` real via `importlib.import_module`. Confirma o caminho de discovery end-to-end; os mocks não pegam isso. Não pular.

## Roadmap

- **v1 (esta spec):** contrato `ResourceProvider` + `ResourceRegistry.discover()` + discovery via plugin in-tree + Platform migrado.
- **v2:** `CrdFilesystemLoader` (lê `crds/*.yaml` local ou do gitops, gera provider via `pydantic.create_model()`) + abstração `Loader` + resolução de conflito de nomes.
- **v3:** `CrdClusterLoader` (CRDs anotados via API K8s) + hot-reload (descoberta sem rollout restart).

## Out of scope (non-decisions)

- Abstração `Loader` separada — não criada no v1; `discover()` resolve direto a lista `PROVIDERS`. Extrair quando o 2º loader chegar.
- Resolução de conflito de nomes — v2.
- Hot-reload / descoberta sem restart — v2+.
- Plugin externo (polirepo) — fora de escopo. A lista in-tree `PROVIDERS` só registra providers da própria árvore; um plugin externo exigiria outro mecanismo (entry points, que por sua vez exigiriam tornar o projeto pacote instalável). Reavaliar se/quando o caso polirepo surgir.
- Generalização de `watcher.py` / `GitOpsCommitter` para múltiplos CRDs — já fora de escopo no refactor anterior; permanece.
- Migração futura para MCP (abordagem 4 do brief) — sustentada pelo contrato: um `MCPProvider` que satisfaz o mesmo Protocol (`tools()` faz proxy de chamadas MCP) entra sem refactor.

# CRD Cluster

**Status:** Approved  
**Date:** 2026-06-02

## Overview

Adicionar suporte ao recurso `Cluster` seguindo o padrão estabelecido por `Platform`. O agente commita um manifesto `Cluster` no repositório GitOps; o Crossplane (via Composition) reconcilia e gera um ConfigMap. O `Cluster` é um recurso independente — sem referência a `Platform`.

## Manifesto gerado

```yaml
apiVersion: wasp.silvios.me/v1alpha1
kind: Cluster
metadata:
  name: <name>
spec:
  kubernetesVersion: "1.34"
```

Path GitOps: `infrastructure/clusters/{name}.yaml`

## Componentes novos

### `wasp/resources/cluster/`

- `manifest.py` — `ClusterManifest`, `ClusterSpec(kubernetesVersion: str = "1.34")`, constantes `CLUSTER_GROUP = "wasp.silvios.me"`, `CLUSTER_VERSION = "v1alpha1"`, `CLUSTER_PLURAL = "clusters"`
- `provisioner.py` — `ClusterProvisioner`, `DEFAULT_KUBERNETES_VERSION = "1.34"`; commita em `infrastructure/clusters/{name}.yaml`; spawna watcher após commit bem-sucedido
- `inventory.py` — `ClusterInventory` com `list()` e `get()`; status via condição `Ready`; mensagens: `"O Cluster {name} está {status} desde {dd/mm}."` / `"Nenhum Cluster encontrado com o nome {name}."`
- `provider.py` — `ClusterProvider(name="cluster")` retorna `[provision_cluster_instance, list_cluster_instances, get_cluster_status]`
- `__init__.py` — re-exports explícitos com alias (`as`)

### `wasp/provision.py`

Três novas `@tool`:

- `provision_cluster_instance(name, kubernetes_version="1.34", requested_by="", run_context=None)`
- `list_cluster_instances(run_context=None)`
- `get_cluster_status(name, run_context=None)`

### `wasp/watcher.py`

Adicionar ao arquivo existente, sem refatoração genérica (2 CRDs não justificam abstração):

- `watch_cluster(name, chat_id, notifier, parent_span_ctx)` + `_watch_cluster_inner` — mesma estrutura de `watch_platform`, usando `CLUSTER_*` e `cluster_ready_message`
- `cluster_ready_message(name, cluster) -> str` — `"Cluster '{name}' está pronto (Kubernetes {version})."`; `version` vem de `cluster["spec"]["kubernetesVersion"]`
- `ClusterWatcherSpawner` — idêntico a `PlatformWatcherSpawner`, chama `watch_cluster`

### `wasp/resources/registry.py`

Adicionar `"wasp.resources.cluster.provider:ClusterProvider"` à lista `PROVIDERS`.

### `tests/conftest.py`

Adicionar módulos `wasp.resources.cluster`, `wasp.resources.cluster.manifest`, `wasp.resources.cluster.inventory`, `wasp.resources.cluster.provisioner`, `wasp.resources.cluster.provider` ao loop `mock_agno` (setup e teardown).

## Testes

- `tests/test_cluster_manifest.py` — build correto, saída YAML válida
- `tests/test_cluster_inventory.py` — list transforma items, get retorna status/message, unauthorized, not_found, error
- `tests/test_cluster_provider.py` — name, tools, satisfaz Protocol
- `tests/test_provision.py` — provision_cluster_instance (commit path, watcher spawned, auth), list_cluster_instances, get_cluster_status (span, not_found, unauthorized)

## Não incluído

- Watcher genérico (premature abstraction para 2 CRDs — revisar se surgir terceiro)
- XRD/Composition Crossplane (fora do escopo do agente)
- Operações de update/delete (backlog)
# Resource Provider Extensibility (v1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir adicionar novos Custom Resources ao wasp-agent sem editar `agent.py`/`provision.py`, via um contrato `ResourceProvider` (Protocol) descoberto por `ResourceRegistry.discover()` sobre plugin discovery do Python.

**Architecture:** Cada recurso expõe um `ResourceProvider` (atributo `name` + método `tools()`) registrado in-tree em `[project.entry-points."wasp_agent.resources"]` do `pyproject.toml`. No boot, `ResourceRegistry.discover()` varre os entry points, instancia os providers, e `all_tools()` agrega as `@tool` de todos. `agent.py` monta `tools=ResourceRegistry.discover().all_tools()` em vez da lista fixa atual.

**Tech Stack:** Python 3.14, `importlib.metadata`, Pydantic, Agno, pytest (mocks via `mock_agno` fixture), ruff, uv.

**Spec:** `docs/sdlc/02-design/2026-05-31-resource-provider-extensibility.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `wasp/resources/protocol.py` (novo) | `ResourceProvider` Protocol — `name: str` + `tools() -> list[Callable]` |
| `wasp/resources/registry.py` (novo) | `ResourceRegistry` — `discover()` (plugin discovery) + `all_tools()` (agregação) |
| `wasp/resources/platform/provider.py` (novo, folha não reexportada) | `PlatformProvider` — wrapper fino sobre as `@tool` existentes |
| `pyproject.toml` (modificado) | `[project.entry-points."wasp_agent.resources"]` aponta `platform` → `PlatformProvider` |
| `wasp/agent.py` (modificado) | `tools=ResourceRegistry.discover().all_tools()` |
| `tests/test_registry.py` (novo) | Cobre `discover()` e `all_tools()` |
| `tests/test_platform_provider.py` (novo) | Cobre `PlatformProvider.name` e `tools()` |
| `tests/conftest.py` (modificado) | Novos módulos nas duas listas `sys.modules.pop` |

**Ordem de implementação (TDD, `make test` verde a cada commit):**
Task 1 (Protocol) → Task 2 (Registry) → Task 3 (conftest) → Task 4 (PlatformProvider) → Task 5 (entry point) → Task 6 (agent.py migração) → Task 7 (validação final).

---

## Task 1: ResourceProvider Protocol

**Files:**
- Create: `wasp/resources/protocol.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Criar `tests/test_registry.py` com:

```python
def test_resource_provider_protocol_runtime_checkable(mock_agno):
    from collections.abc import Callable
    from wasp.resources.protocol import ResourceProvider

    class FakeProvider:
        name = "fake"

        def tools(self) -> list[Callable]:
            return []

    assert isinstance(FakeProvider(), ResourceProvider)


def test_resource_provider_rejects_non_conforming(mock_agno):
    from wasp.resources.protocol import ResourceProvider

    class NotAProvider:
        pass

    assert not isinstance(NotAProvider(), ResourceProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'wasp.resources.protocol'`

- [ ] **Step 3: Write minimal implementation**

Criar `wasp/resources/protocol.py`:

```python
from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class ResourceProvider(Protocol):
    name: str

    def tools(self) -> list[Callable]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_registry.py -v`
Expected: PASS (2 passed)

Nota: `runtime_checkable` com Protocol só verifica presença dos membros, não assinaturas. `test_resource_provider_rejects_non_conforming` passa porque `NotAProvider` não tem `name` nem `tools`.

- [ ] **Step 5: Commit**

```bash
git add wasp/resources/protocol.py tests/test_registry.py
git commit -m "feat(resources): add ResourceProvider protocol"
```

---

## Task 2: ResourceRegistry (discover + all_tools)

**Files:**
- Create: `wasp/resources/registry.py`
- Test: `tests/test_registry.py` (adiciona casos)

`discover()` usa `importlib.metadata.entry_points(group="wasp_agent.resources")`. Cada entry point resolve (`.load()`) para a **classe** provider, que é instanciada. Loga em INFO a contagem e os nomes.

- [ ] **Step 1: Write the failing test**

Adicionar a `tests/test_registry.py`:

```python
def test_all_tools_aggregates_providers(mock_agno):
    from wasp.resources.registry import ResourceRegistry

    def tool_a():
        return "a"

    def tool_b():
        return "b"

    def tool_c():
        return "c"

    class ProviderOne:
        name = "one"

        def tools(self):
            return [tool_a, tool_b]

    class ProviderTwo:
        name = "two"

        def tools(self):
            return [tool_c]

    registry = ResourceRegistry([ProviderOne(), ProviderTwo()])

    assert registry.all_tools() == [tool_a, tool_b, tool_c]


def test_all_tools_empty_when_no_providers(mock_agno):
    from wasp.resources.registry import ResourceRegistry

    registry = ResourceRegistry([])

    assert registry.all_tools() == []


def test_discover_loads_providers_from_entry_points(mock_agno, monkeypatch):
    from importlib.metadata import EntryPoint
    from wasp.resources import registry as registry_mod
    from wasp.resources.registry import ResourceRegistry

    def tool_x():
        return "x"

    class DiscoveredProvider:
        name = "discovered"

        def tools(self):
            return [tool_x]

    fake_ep = EntryPoint(
        name="discovered",
        value="irrelevant:DiscoveredProvider",
        group="wasp_agent.resources",
    )
    monkeypatch.setattr(fake_ep, "load", lambda: DiscoveredProvider, raising=False)
    monkeypatch.setattr(
        registry_mod, "entry_points", lambda group: [fake_ep]
    )

    registry = ResourceRegistry.discover()

    assert registry.all_tools() == [tool_x]


def test_discover_empty_when_no_entry_points(mock_agno, monkeypatch):
    from wasp.resources import registry as registry_mod
    from wasp.resources.registry import ResourceRegistry

    monkeypatch.setattr(registry_mod, "entry_points", lambda group: [])

    registry = ResourceRegistry.discover()

    assert registry.all_tools() == []
```

Nota: `EntryPoint` é um `NamedTuple`; `monkeypatch.setattr(fake_ep, "load", ...)` substitui o método na instância. `entry_points` é importado no módulo `registry` (não chamado via `importlib.metadata.entry_points`) para que o `monkeypatch.setattr(registry_mod, "entry_points", ...)` funcione.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'wasp.resources.registry'`

- [ ] **Step 3: Write minimal implementation**

Criar `wasp/resources/registry.py`:

```python
import logging
from collections.abc import Callable
from importlib.metadata import entry_points

from wasp.resources.protocol import ResourceProvider

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "wasp_agent.resources"


class ResourceRegistry:
    def __init__(self, providers: list[ResourceProvider]):
        self._providers = providers

    @classmethod
    def discover(cls) -> "ResourceRegistry":
        providers = [ep.load()() for ep in entry_points(group=ENTRY_POINT_GROUP)]
        log.info(
            "discovered %d resource providers: %s",
            len(providers),
            [p.name for p in providers],
        )
        return cls(providers)

    def all_tools(self) -> list[Callable]:
        return [tool for provider in self._providers for tool in provider.tools()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_registry.py -v`
Expected: PASS (6 passed — 2 da Task 1 + 4 novos)

- [ ] **Step 5: Commit**

```bash
git add wasp/resources/registry.py tests/test_registry.py
git commit -m "feat(resources): add ResourceRegistry with discover and all_tools"
```

---

## Task 3: Registrar novos módulos no conftest

`tests/conftest.py` tem duas listas `sys.modules.pop` (setup ~linha 88-93 e teardown ~linha 180-185). Sem registrar os novos módulos, estado vaza entre testes (ver `tests/CLAUDE.md`). Fazer antes de Task 4 para a fixture já limpar `provider.py`.

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Adicionar os três módulos novos em AMBAS as listas**

Em cada uma das duas tuplas de `sys.modules.pop`, logo após a linha `"wasp.resources.platform.provisioner",`, adicionar:

```python
        "wasp.resources.protocol",
        "wasp.resources.registry",
        "wasp.resources.platform.provider",
```

(Aplicar nas duas ocorrências — setup e teardown.)

- [ ] **Step 2: Run the suite to verify nothing broke**

Run: `uv run pytest tests/test_registry.py -v`
Expected: PASS (6 passed) — módulos ainda não usados, mas a lista não quebra nada.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: register new resource modules in conftest sys.modules.pop"
```

---

## Task 4: PlatformProvider

**Files:**
- Create: `wasp/resources/platform/provider.py`
- Test: `tests/test_platform_provider.py`

`provider.py` é **módulo folha** — NÃO reexportado em `wasp/resources/platform/__init__.py` (evita ciclo de import, ver spec).

- [ ] **Step 1: Write the failing test**

Criar `tests/test_platform_provider.py`:

```python
def test_platform_provider_name(mock_agno):
    from wasp.resources.platform.provider import PlatformProvider

    assert PlatformProvider().name == "platform"


def test_platform_provider_tools(mock_agno):
    from wasp.provision import (
        list_platform_instances,
        provision_platform_instance,
    )
    from wasp.resources.platform.provider import PlatformProvider

    tools = PlatformProvider().tools()

    assert tools == [provision_platform_instance, list_platform_instances]


def test_platform_provider_satisfies_protocol(mock_agno):
    from wasp.resources.platform.provider import PlatformProvider
    from wasp.resources.protocol import ResourceProvider

    assert isinstance(PlatformProvider(), ResourceProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_platform_provider.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'wasp.resources.platform.provider'`

- [ ] **Step 3: Write minimal implementation**

Criar `wasp/resources/platform/provider.py`:

```python
from collections.abc import Callable

from wasp.provision import list_platform_instances, provision_platform_instance


class PlatformProvider:
    name = "platform"

    def tools(self) -> list[Callable]:
        return [provision_platform_instance, list_platform_instances]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_platform_provider.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add wasp/resources/platform/provider.py tests/test_platform_provider.py
git commit -m "feat(resources): add PlatformProvider wrapping platform tools"
```

---

## Task 5: Registrar o entry point no pyproject.toml

**Files:**
- Modify: `pyproject.toml`

Sem `[build-system]`/instalação editável, `importlib.metadata.entry_points` não enxerga o entry point em runtime. O projeto roda via `uv`; após adicionar o entry point é preciso reinstalar o pacote (`uv sync` / `uv pip install -e .`) para o metadata ser regravado. A validação real acontece no e2e (Task 7), que importa o `main.py` real.

- [ ] **Step 1: Adicionar a seção de entry points**

Em `pyproject.toml`, após o bloco `[project]` (antes de `[dependency-groups]`), adicionar:

```toml
[project.entry-points."wasp_agent.resources"]
platform = "wasp.resources.platform.provider:PlatformProvider"
```

- [ ] **Step 2: Reinstalar para registrar o metadata**

Run: `uv sync`
Expected: instala/atualiza o pacote `wasp-agent` em modo editável sem erro.

- [ ] **Step 3: Verificar que o entry point é descoberto**

Run:
```bash
uv run python -c "from importlib.metadata import entry_points; print([(e.name, e.value) for e in entry_points(group='wasp_agent.resources')])"
```
Expected: `[('platform', 'wasp.resources.platform.provider:PlatformProvider')]`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(resources): register platform provider entry point"
```

(Se `uv.lock` não mudou, comitar só `pyproject.toml`.)

---

## Task 6: Migrar agent.py para o registry

**Files:**
- Modify: `wasp/agent.py:1-3` (imports) e `wasp/agent.py:39` (linha `tools=...`)
- Test: `tests/test_agent.py` (já existe `test_build_agent_tools` — guia da migração)

O teste `test_build_agent_tools` já valida que `list_platform_instances` e `provision_platform_instance` estão em `tools`. Ele deve continuar verde após a migração — é a rede de segurança contra regressão.

Problema de discovery sob mock: `ResourceRegistry.discover()` chama `entry_points(group=...)`. Sob `mock_agno`, o pacote está instalado (Task 5 rodou `uv sync`), então o entry point real `platform` É descoberto e `PlatformProvider().tools()` retorna as duas funções `@tool` reais. Logo `test_build_agent_tools` passa sem mock adicional do registry.

- [ ] **Step 1: Verificar o teste de regressão passa ANTES da mudança**

Run: `uv run pytest tests/test_agent.py::test_build_agent_tools -v`
Expected: PASS (estado atual — lista fixa).

- [ ] **Step 2: Aplicar a migração em `wasp/agent.py`**

Trocar o import (linhas 1-3):

```python
# remover:
from wasp import list_platform_instances, provision_platform_instance

# o cabeçalho fica:
from agno.agent import Agent

from wasp.models import build_model
from wasp.resources.registry import ResourceRegistry
from wasp.sessions import build_session_db
```

Trocar a linha de tools dentro de `build_agent()` (era `tools=[provision_platform_instance, list_platform_instances]`):

```python
        tools=ResourceRegistry.discover().all_tools(),
```

- [ ] **Step 3: Run the regression test**

Run: `uv run pytest tests/test_agent.py -v`
Expected: PASS (3 passed). `test_build_agent_tools` confirma que ambas as tools continuam presentes, agora montadas via registry.

- [ ] **Step 4: Run the full unit suite**

Run: `make test`
Expected: todos passam, cobertura 100%. (Baseline anterior: 326 passed, 1 skipped; agora maior pelos novos testes.)

- [ ] **Step 5: Commit**

```bash
git add wasp/agent.py
git commit -m "feat(agent): build tools from ResourceRegistry.discover()"
```

---

## Task 7: Validação final (format + test + e2e)

**Files:** nenhum (validação).

O e2e importa o `main.py` real e exercita `discover()` → tools com o entry point realmente instalado — a única validação que confirma o registro no `pyproject.toml` (mocks não pegam isso, ver spec/CLAUDE.md).

- [ ] **Step 1: Format**

Run: `make format`
Expected: ruff formata/limpa sem erros pendentes.

- [ ] **Step 2: Lint**

Run: `ruff check .`
Expected: `All checks passed!`

- [ ] **Step 3: Unit + coverage**

Run: `make test`
Expected: todos passam, cobertura 100% (`fail_under = 100`).

- [ ] **Step 4: End-to-end**

Run: `make e2e-with-debug`
Expected: fluxo completo verde. Confirma que `ResourceRegistry.discover()` encontra o `PlatformProvider` via entry point instalado e o agente expõe as tools no caminho real.

- [ ] **Step 5: Atualizar CLAUDE.md (seção `wasp/resources/`)**

Em `CLAUDE.md`, na seção "Packages — `wasp/resources/`", adicionar nota sobre o novo padrão de provider:

```markdown
Novo CRD agora também registra um `ResourceProvider` em `wasp/resources/<kind>/provider.py`
(módulo folha, não reexportado no `__init__.py` para evitar ciclo) e adiciona uma linha em
`[project.entry-points."wasp_agent.resources"]` no `pyproject.toml`. `agent.py` monta as tools
via `ResourceRegistry.discover().all_tools()` — não editar `agent.py` para um novo recurso.
Após adicionar o entry point, rodar `uv sync` para registrar o metadata.
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document ResourceProvider extensibility pattern"
```

---

## Self-Review

**Spec coverage:**
- Contrato `ResourceProvider` → Task 1. ✅
- `ResourceRegistry.discover()` + `all_tools()` → Task 2. ✅
- Log INFO da contagem → Task 2 (Step 3). ✅
- `PlatformProvider` wrapper fino, módulo folha não reexportado → Task 4. ✅
- Entry point in-tree no `pyproject.toml` → Task 5. ✅
- `agent.py` monta via registry (walk-skeleton) → Task 6. ✅
- Error handling — entry point quebrado propaga (fail-fast): comportamento default de `ep.load()`, não requer código extra; lista vazia coberta em `test_discover_empty_when_no_entry_points`. ✅
- Testes `test_registry.py` + `test_platform_provider.py` + conftest → Tasks 2,3,4. ✅
- e2e exercita discovery real → Task 7. ✅
- CLAUDE.md atualizado → Task 7 (Step 5). ✅
- Deployment (rollout restart) — decisão documentada na spec; sem ação de código no v1. ✅

**Placeholder scan:** nenhum TBD/TODO; todo passo de código tem o código completo.

**Type consistency:** `ResourceProvider` (`name: str`, `tools() -> list[Callable]`), `ResourceRegistry(providers)`, `.discover()`, `.all_tools()`, `ENTRY_POINT_GROUP = "wasp_agent.resources"`, `PlatformProvider` (`name = "platform"`, `tools()`) — consistentes entre todas as tasks e com o `pyproject.toml`.

**Não-decisões (fora de escopo, conforme spec):** abstração `Loader`, resolução de conflito de nomes, hot-reload, plugin externo (polirepo), `CrdFilesystemLoader`/`CrdClusterLoader` — nenhuma task os implementa, por design.

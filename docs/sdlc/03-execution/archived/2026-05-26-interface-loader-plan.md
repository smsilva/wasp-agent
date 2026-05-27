# InterfaceLoader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extrair a construção de interfaces agno de `main.py` para uma classe `InterfaceLoader` que lê variáveis de ambiente por conta própria.

**Architecture:** `InterfaceLoader(agent).build()` retorna a lista de interfaces configuradas. Cada canal é um método privado `_build_<canal>(self) -> Interface | None`. `main.py` substitui o bloco de 6 linhas por uma única chamada.

**Tech Stack:** Python 3.14, agno (`agno.os.interfaces.telegram.Telegram`), pytest, ruff

---

## File Map

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `wasp/clients/interfaces.py` | Criar | `InterfaceLoader` |
| `tests/test_interface_loader.py` | Criar | Testes unitários de `InterfaceLoader` |
| `tests/conftest.py` | Modificar | Adicionar `wasp.clients.interfaces` à lista de módulos limpos |
| `main.py` | Modificar | Usar `InterfaceLoader(agent).build()` |
| `tests/test_main.py` | Modificar | Adaptar testes que testam construção de interfaces via `import main` |

---

### Task 1: Registrar `wasp.clients.interfaces` no conftest

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Adicionar o novo módulo à lista de limpeza do fixture `mock_agno`**

Em `tests/conftest.py`, há dois blocos `for mod in (...)` — um antes do `yield` e um depois. Adicionar `"wasp.clients.interfaces"` em ambos, logo após `"wasp.clients.telegram.webhook"`:

```python
# Antes do yield (e depois também — mesma lista):
        "wasp.clients.telegram.webhook",
        "wasp.clients.interfaces",   # <-- adicionar aqui
        "wasp.clients.local",
```

- [ ] **Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "test(conftest): register wasp.clients.interfaces for module cleanup"
```

---

### Task 2: Criar `InterfaceLoader` com TDD

**Files:**
- Create: `tests/test_interface_loader.py`
- Create: `wasp/clients/interfaces.py`

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_interface_loader.py`:

```python
from unittest.mock import MagicMock, patch


def test_build_returns_telegram_when_token_set(mock_agno, monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-123")
    from wasp.clients.interfaces import InterfaceLoader

    agent = MagicMock()
    with patch("wasp.clients.interfaces._install_start_token_handler"):
        result = InterfaceLoader(agent).build()

    assert len(result) == 1
    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_called_once_with(
        agent=agent, token="tok-123"
    )


def test_build_returns_empty_list_when_no_token(mock_agno, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    from wasp.clients.interfaces import InterfaceLoader

    agent = MagicMock()
    result = InterfaceLoader(agent).build()

    assert result == []
    mock_agno["agno.os.interfaces.telegram"].Telegram.assert_not_called()


def test_build_installs_start_token_handler(mock_agno, monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok-abc")
    from wasp.clients.interfaces import InterfaceLoader

    agent = MagicMock()
    with patch("wasp.clients.interfaces._install_start_token_handler") as mock_install:
        InterfaceLoader(agent).build()

    mock_install.assert_called_once()
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

```bash
pytest tests/test_interface_loader.py -v
```

Esperado: `FAILED` com `ModuleNotFoundError: No module named 'wasp.clients.interfaces'`

- [ ] **Step 3: Implementar `wasp/clients/interfaces.py`**

```python
import os

from agno.os.interfaces.telegram import Telegram

from wasp.clients.telegram import _install_start_token_handler


class InterfaceLoader:
    def __init__(self, agent) -> None:
        self._agent = agent

    def build(self) -> list:
        builders = [self._build_telegram]
        return [iface for b in builders if (iface := b()) is not None]

    def _build_telegram(self) -> Telegram | None:
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            return None
        iface = Telegram(agent=self._agent, token=token)
        _install_start_token_handler(iface)
        return iface
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

```bash
pytest tests/test_interface_loader.py -v
```

Esperado: 3 testes `PASSED`

- [ ] **Step 5: Rodar a suite completa com cobertura**

```bash
pytest --cov -v
```

Esperado: todos os testes passam, coverage 100%

- [ ] **Step 6: Commit**

```bash
git add wasp/clients/interfaces.py tests/test_interface_loader.py
git commit -m "feat(clients): add InterfaceLoader"
```

---

### Task 3: Atualizar `main.py`

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Substituir o bloco de interfaces em `main.py`**

Remover as linhas 16 e 19 (imports de `Telegram` e `_install_start_token_handler`) e o bloco das linhas 25–30. Adicionar o import de `InterfaceLoader` e a chamada:

```python
# Remover:
from agno.os.interfaces.telegram import Telegram  # noqa: E402
from wasp.clients.telegram import _install_start_token_handler  # noqa: E402

# e o bloco:
interfaces = []
telegram_token = os.getenv("TELEGRAM_TOKEN")
if telegram_token:
    telegram_interface = Telegram(agent=agent, token=telegram_token)
    _install_start_token_handler(telegram_interface)
    interfaces.append(telegram_interface)

# Substituir por:
from wasp.clients.interfaces import InterfaceLoader  # noqa: E402

interfaces = InterfaceLoader(agent).build()
```

O arquivo `main.py` deve ficar assim após a mudança (trecho relevante):

```python
from agno.os import AgentOS  # noqa: E402
from wasp import auth  # noqa: E402
from wasp.agent import build_agent  # noqa: E402
from wasp.clients.interfaces import InterfaceLoader  # noqa: E402

auth.init_db()

agent = build_agent()

interfaces = InterfaceLoader(agent).build()
```

- [ ] **Step 2: Adaptar `tests/test_main.py`**

Os testes `test_agent_os_with_token`, `test_telegram_not_added_without_token` e `test_install_start_token_handler_called_with_token` testam comportamento que agora pertence a `InterfaceLoader`. Eles continuam válidos como testes de integração via `import main`, mas a asserção sobre `Telegram.assert_called_once_with` precisa apontar para o mock correto.

Verificar que os três testes ainda passam sem alteração. Se algum falhar por mudança de caminho do mock, atualizar o `monkeypatch.setattr` para apontar para `wasp.clients.interfaces.Telegram` em vez de `agno.os.interfaces.telegram.Telegram`.

- [ ] **Step 3: Rodar lint**

```bash
ruff check .
```

Esperado: nenhum erro.

- [ ] **Step 4: Rodar suite completa**

```bash
pytest --cov -v
```

Esperado: todos os testes passam, coverage 100%

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "refactor(main): use InterfaceLoader to build agno interfaces"
```

---

### Task 4: Validação final

- [ ] **Step 1: Rodar format + test + e2e**

```bash
make format
make test
make e2e-with-debug
```

Esperado: tudo verde.

- [ ] **Step 2: Commit de encerramento (se `make format` gerar diff)**

```bash
git add -u
git commit -m "style: apply ruff format after InterfaceLoader refactor"
```
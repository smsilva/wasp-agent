# agno API — Notas do Ciclo 1

**Data:** 2026-05-13
**Versão testada:** agno 2.6.5

---

## Divergências entre documentação e API instalada

A documentação oficial do agno (docs.agno.com) frequentemente fica desatualizada em relação ao pacote publicado. Antes de escrever código, sempre verifique os caminhos reais em `.venv/lib/python*/site-packages/agno/`.

### SQLite storage

| Documentação / planos antigos | API real (agno 2.6.5) |
|-------------------------------|----------------------|
| `from agno.storage.agent.sqlite import SqliteAgentStorage` | `from agno.db.sqlite.sqlite import SqliteDb` |
| `storage=SqliteAgentStorage(db_file=..., table_name=...)` | `db=SqliteDb(db_file=..., session_table=...)` |

`SqliteDb` requer `sqlalchemy>=2.0` — declare como dependência explícita no `pyproject.toml`.

### Histórico de conversa

| Documentação / planos antigos | API real (agno 2.6.5) |
|-------------------------------|----------------------|
| `add_history_to_messages=True` | `add_history_to_context=True` |

### Caminhos de import confirmados (agno 2.6.5)

```python
from agno.agent import Agent                          # ✅
from agno.models.anthropic import Claude              # ✅
from agno.os import AgentOS                           # ✅
from agno.os.interfaces.telegram import Telegram      # ✅
from agno.db.sqlite.sqlite import SqliteDb            # ✅
```

---

## Dependências do agno: use extras, não pacotes individuais

O agno organiza dependências opcionais em extras. Declarar `anthropic`, `fastapi`, `uvicorn`, `pyTelegramBotAPI` individualmente **não funciona** — o agno os importa de forma condicional e pode não encontrá-los pelo caminho esperado.

Use o extra composto correto para este projeto:

```toml
"agno[anthropic,os,telegram]>=2.0.0"
```

| Extra | O que inclui |
|-------|-------------|
| `anthropic` | `anthropic` SDK |
| `os` | `fastapi[standard]`, `uvicorn` |
| `telegram` | `pyTelegramBotAPI>=4.32.0`, `aiohttp` |

`sqlalchemy` não está em nenhum extra do agno — declare explicitamente (requerido por `SqliteDb`).

---

## Telegram: agent é obrigatório no construtor

A interface `Telegram` exige que o `agent` seja passado diretamente no construtor. **Não** é suficiente passar o agent via `AgentOS`.

```python
# ❌ Errado — lança ValueError: "Telegram requires an agent, team, or workflow"
interfaces.append(Telegram(token=token))

# ✅ Correto
interfaces.append(Telegram(agent=agent, token=token))
```

Por isso, o `agent` deve ser criado **antes** das interfaces:

```python
agent = Agent(...)

interfaces = []
if telegram_token:
    interfaces.append(Telegram(agent=agent, token=telegram_token))
```

Ao adicionar Discord ou outros canais no ciclo 2, aplicar o mesmo padrão.

---

## load_dotenv precisa ser mockado nos testes

Se o projeto tiver um `.env` real com `TELEGRAM_TOKEN` preenchido, o `load_dotenv()` chamado durante `import main` vai carregar o token no `os.environ` — **sobrescrevendo** qualquer `monkeypatch.delenv` feito antes do import.

A solução é mockar `dotenv.load_dotenv` no fixture do conftest, antes de `import main`:

```python
monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
```

**Por que `dotenv.load_dotenv` e não `dotenv.main.load_dotenv`?**

`main.py` faz `from dotenv import load_dotenv`, que resolve pelo namespace do pacote (`dotenv.__init__`). Patchear `dotenv.main.load_dotenv` não afeta a referência já exportada. O alvo correto é `dotenv.load_dotenv`.

---

## Configuração do pytest

`main.py` fica na raiz do projeto, não em `src/`. O pytest não adiciona a raiz ao `sys.path` automaticamente. Sem `pythonpath = ["."]`, `import main` nos testes falha mesmo com `main.py` existindo.

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

---

## Mock de módulos agno nos testes

Para evitar chamadas reais à API do Telegram e ao LLM proxy, `main.py` é importado com os módulos do agno mockados via `sys.modules`.

**Regra:** incluir tanto os módulos folha quanto todos os pacotes pai. O Python resolve a hierarquia de pacotes ao importar.

```python
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
]
```

O fixture faz `sys.modules.pop("main", None)` antes e depois do yield para garantir que cada teste reimporte `main` com mocks frescos.

---

## ruff: violações intencionais

### E402 em main.py

`load_dotenv()` deve rodar antes dos imports do agno para que as variáveis de ambiente estejam disponíveis quando o SDK inicializa. Isso viola a regra E402 do ruff ("module level import not at top of file"). Suprima com `# noqa: E402` em cada import agno.

```python
load_dotenv()

from agno.agent import Agent              # noqa: E402
from agno.models.anthropic import Claude  # noqa: E402
# ...
```

### F401 em testes

`import main` dentro de funções de teste é um import por efeito colateral (força a execução do código de módulo com os mocks ativos). O ruff não reconhece esse padrão e sinaliza F401. Suprima com `# noqa: F401`.

```python
def test_agent_config(mock_agno):
    import main  # noqa: F401
    # ...
```

---

## Checklist para ciclos futuros

Ao adicionar um novo canal (Discord, Slack, etc.):

- [ ] Verificar o caminho de import real do novo `Interface` em `.venv/lib/`
- [ ] Adicionar o módulo e seus pacotes pai ao `AGNO_MODULES` no conftest
- [ ] Adicionar teste para o novo canal (com token) e sem token
- [ ] Verificar se o agno tem extra para o novo canal (ex: `agno[discord]`) antes de declarar deps individuais
- [ ] Verificar se a nova interface exige `agent=` no construtor (padrão do Telegram — provavelmente igual)
- [ ] Manter `Agent` e `AgentOS` intocados — toda lógica de canal fica em `interfaces`
- [ ] `ruff check .` limpo antes de commitar

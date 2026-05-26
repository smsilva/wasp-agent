# Design: Pacote `wasp/clients/`

**Date:** 2026-05-26  
**Status:** Approved  
**Scope:** Reorganização de `wasp/notifier.py` e `wasp/telegram.py` em subpacotes por canal

## Contexto

O código específico do Telegram está espalhado em dois arquivos (`wasp/notifier.py` e `wasp/telegram.py`) junto com código genérico (`Notifier` Protocol, `ConsoleNotifier`, `RecordingNotifier`). À medida que novos canais (Discord, Slack) forem adicionados, essa estrutura não escala.

## Estrutura alvo

```
wasp/
  clients/
    __init__.py          ← Notifier Protocol
    telegram/
      __init__.py        ← re-exports: TelegramNotifier, _install_start_token_handler
      notifier.py        ← TelegramNotifier
      webhook.py         ← _process_start_token, _install_start_token_handler
    local/
      __init__.py        ← re-export: ConsoleNotifier
      notifier.py        ← ConsoleNotifier

tests/
  notifiers.py           ← RecordingNotifier (test double)
```

Arquivos deletados: `wasp/notifier.py`, `wasp/telegram.py`

## O que move para onde

| Símbolo | Origem | Destino |
|---|---|---|
| `Notifier` Protocol | `wasp/notifier.py` | `wasp/clients/__init__.py` |
| `TelegramNotifier` | `wasp/notifier.py` | `wasp/clients/telegram/notifier.py` |
| `_process_start_token` | `wasp/telegram.py` | `wasp/clients/telegram/webhook.py` |
| `_install_start_token_handler` | `wasp/telegram.py` | `wasp/clients/telegram/webhook.py` |
| `ConsoleNotifier` | `wasp/notifier.py` | `wasp/clients/local/notifier.py` |
| `RecordingNotifier` | `wasp/notifier.py` | `tests/notifiers.py` |

## Mudanças de import

### Produção

| Arquivo | Import atual | Import novo |
|---|---|---|
| `wasp/watcher.py` | `from wasp.notifier import ConsoleNotifier, Notifier, TelegramNotifier` | `from wasp.clients import Notifier` + `from wasp.clients.telegram import TelegramNotifier` + `from wasp.clients.local import ConsoleNotifier` |
| `main.py` | `from wasp.telegram import _install_start_token_handler` | `from wasp.clients.telegram import _install_start_token_handler` |

### Testes

| Arquivo | Import atual | Import novo |
|---|---|---|
| `tests/test_telegram.py` | `from wasp.telegram import ...` | `from wasp.clients.telegram import ...` |
| `tests/test_watcher.py` | `from wasp.notifier import ...` | `from wasp.clients.{telegram,local} import ...` + `from tests.notifiers import RecordingNotifier` |
| `tests/e2e/conftest.py` | `from wasp.notifier import RecordingNotifier` | `from tests.notifiers import RecordingNotifier` |

### `tests/conftest.py` — `sys.modules.pop`

Substituir `wasp.notifier` e `wasp.telegram` por:
```
"wasp.clients",
"wasp.clients.telegram",
"wasp.clients.telegram.notifier",
"wasp.clients.telegram.webhook",
"wasp.clients.local",
"wasp.clients.local.notifier",
```

## `__init__.py` exports

**`wasp/clients/telegram/__init__.py`:**
```python
from wasp.clients.telegram.notifier import TelegramNotifier
from wasp.clients.telegram.webhook import _install_start_token_handler
```

**`wasp/clients/local/__init__.py`:**
```python
from wasp.clients.local.notifier import ConsoleNotifier
```

## Tarefas adicionais pós-refatoração

- Atualizar `CLAUDE.md` com a estrutura de pacotes preferida (`wasp/clients/<canal>/`) para guiar adições futuras
- Criar documento de exploração em `docs/sdlc/01-exploration/` descrevendo a extensão do padrão `clients/` para o restante do código

## Validação

```bash
make format
make test           # 100% coverage obrigatório
make e2e-with-debug # cobre bugs que make test não pega (router real do agno, prefixo /telegram)
```

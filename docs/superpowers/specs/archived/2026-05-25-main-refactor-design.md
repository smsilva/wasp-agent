**Date:** 2026-05-25  
**Status:** Implemented  
**Scope:** `main.py`, `wasp/`, `tests/`

# Design: Refatoração de `main.py`

## Motivation

`main.py` acumula quatro responsabilidades distintas: bootstrap, factory de modelo LLM,
definição do agente, e middleware Telegram de autenticação. A extração melhora organização
(B), testabilidade independente de cada unidade (A), e reutilização em futuros entrypoints
como CLI ou canal Discord (C).

## New Modules

### `wasp/models.py`

Factory pública `build_model()` que lê `LLM_PROVIDER` do ambiente e retorna a instância
agno correspondente (Ollama, Claude, OpenAIChat). Renomeada de `_build_model` para pública
por ser a API do módulo.

### `wasp/agent.py`

Contém `INSTRUCTIONS` (lista de strings do system prompt) e `build_agent()` — factory
pública que chama `build_model()`, constrói o `SqliteDb` e retorna o `Agent` configurado
com nome, model, db, histórico e tools.

### `wasp/telegram.py`

Middleware Telegram-specific de autenticação de convites:

- `WELCOME_MESSAGE`, `INVALID_INVITE_MESSAGE` — constantes de mensagem
- `_process_start_token(payload, redeem_fn, send_fn) -> bool` — interpreta deep link `/start <token>`
- `_install_start_token_handler(iface: Telegram) -> None` — wraps `iface.get_router` para interceptar o endpoint `/webhook` antes que agno processe

Funções mantêm prefixo `_` (internas ao módulo).

## `main.py` After Refactor (~40 lines)

Pure wiring:

1. Bootstrap: `load_dotenv`, `configure_logging`, `umask`, `telemetry`
2. `agent = build_agent()`
3. Telegram interface setup com `_install_start_token_handler` se `TELEGRAM_TOKEN` presente
4. `AgentOS` + `app = agent_os.get_app()`
5. Metrics route `/telemetry/prometheus`
6. `__main__` guard

## Test Changes

`test_main.py` hoje testa funções diretamente via `main._process_start_token` e
`main._install_start_token_handler`. Com a extração, os testes de unidade dessas funções
migram para novos arquivos; `test_main.py` fica apenas com testes de wiring.

| Arquivo | Conteúdo |
|---|---|
| `tests/test_models.py` (novo) | `build_model()` — Ollama, Claude, OpenAI, provider desconhecido |
| `tests/test_agent.py` (novo) | `build_agent()` — config do agent, tools, instructions |
| `tests/test_telegram.py` (novo) | `_process_start_token` e `_install_start_token_handler` |
| `tests/test_main.py` (reduzido) | Wiring: AgentOS + interfaces + metrics route + init_db |

Testes de `_process_start_token` e `_install_start_token_handler` que hoje referenciam
`main._process_start_token` / `main._install_start_token_handler` / `main.auth` /
`main.TelegramNotifier` serão atualizados para importar de `wasp.telegram` e `wasp.auth`.

## Constraints

- Nenhuma mudança de comportamento — refatoração pura
- `conftest.py` não muda: `mock_agno` continua mockando `agno.*` e limpando `sys.modules`
- `wasp/__init__.py` não muda: continua exportando apenas `provision_platform_instance` e `list_platform_instances`
- `make format && make test && make e2e-with-debug` devem passar ao final

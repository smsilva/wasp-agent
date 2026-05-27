# Local chat — interagir com o agent via curl

**Date:** 2026-05-20  
**Status:** Implemented  
**Scope:** Habilita validação manual interativa do agent sem Telegram, evolução do smoke test Telegram e base inicial para uma CLI futura (`waspctl agent --chat "..."`).

## Contexto

Hoje há três caminhos de validação (`docs/runbooks/validation.md`):

- **A. `make e2e`** — automatizado, simula Telegram/GitHub/cluster.
- **B. Smoke Telegram** — manual, requer ngrok + bot real.
- **C. Prometheus** — ortogonal.

Para validar manualmente o comportamento do LLM (memória, confirmação) e o ciclo provision + notificação async, hoje só o caminho B funciona — e ele depende de Telegram. Isso atrapalha iteração rápida sobre system prompt, instruções e fluxo de confirmação.

## Problema

Não existe forma de exercitar o agent interativamente, com mensagens em sequência, sem montar o bot Telegram + webhook. Em particular:

- Iterar sobre `INSTRUCTIONS` no `main.py` exige restart + nova mensagem no Telegram a cada vez.
- Validar memória de sessão e confirmação exige roteiro manual no chat.
- Ver a notificação async do watcher (`Platform Ready`) exige Telegram configurado.

## Direção

Reusar o endpoint que o `AgentOS` já expõe (`POST /agents/wasp-agent/runs`, multipart/form-data, sem auth em dev local) com:

1. **`ConsoleNotifier`** — implementação de `Notifier` Protocol que escreve no log do servidor (`make run`), substituindo o `TelegramNotifier` quando não há token.
2. **Seleção dinâmica do notifier** via env var `NOTIFIER=console|telegram`. Default: `telegram` se `TELEGRAM_TOKEN` setado, senão `console`.
3. **`session_id` no formato `local:wasp-agent:<chat_id>`**, simétrico ao `tg:<agent>:<chat_id>` do Telegram. `extract_chat_id` em `wasp/watcher.py` aceita ambos os prefixos.
4. **Script `scripts/local-chat`** — wrapper bash sobre `curl`, persiste `session_id` em `.wasp-cli/session` (cwd-local). Subcomandos:
   - `local-chat MESSAGE` — envia mensagem, imprime resposta
   - `local-chat --new-session` — gera novo `session_id` com `chat_id` UUID
   - `local-chat --session` — mostra o `session_id` atual
5. **Target `make local-chat`** — roda roteiro scripted (oi → memória → criar → confirmar) usando o próprio `scripts/local-chat`. Sai 0 se todos os requests retornaram 200. Sem assert sobre conteúdo do LLM.
6. **Runbook `docs/runbooks/local-chat.md`** — setup + roteiro manual. Update em `docs/runbooks/validation.md` adicionando "Path D — Local chat".

## Arquitetura

### `wasp/notifier.py`

Adiciona `ConsoleNotifier`:

```python
class ConsoleNotifier:
    async def send(self, chat_id: str, text: str) -> None:
        log.info("[NOTIFIER chat_id=%s] %s", chat_id, text)
```

### `wasp/provision.py`

Substituir o bloco atual de seleção:

```python
chat_id = extract_chat_id(run_context)
token = os.getenv("TELEGRAM_TOKEN")
if chat_id and token:
    ...
```

por:

```python
chat_id = extract_chat_id(run_context)
notifier = _select_notifier()
if chat_id and notifier is not None:
    # spawn watcher
```

`_select_notifier()`:

- Lê `NOTIFIER`. Se ausente: `telegram` se `TELEGRAM_TOKEN` setado, senão `console`.
- Retorna instância configurada, ou `None` se `NOTIFIER=telegram` sem `TELEGRAM_TOKEN` (caso degenerado — mesmo comportamento atual, sem watcher).

### `wasp/watcher.py`

`extract_chat_id` aceita prefixos `tg` ou `local`:

```python
if len(parts) >= 3 and parts[0] in ("tg", "local"):
    return parts[2]
```

### `scripts/local-chat`

Bash, dependências: `curl`, `jq`. Não exige Python.

```
local-chat MESSAGE
local-chat --new-session
local-chat --session
```

Persiste em `.wasp-cli/session` (cwd-local) — evita estado entre projetos. Formato do arquivo: uma linha com o `session_id`.

Parse da resposta SSE para extrair só o `content` do evento `RunCompleted` (equivalente ao `sse_content` em `tests/e2e/conftest.py`, em bash).

Variáveis de ambiente:

- `WASP_AGENT_URL` (default `http://localhost:7777`)
- `WASP_AGENT_ID` (default `wasp-agent`)

### `Makefile`

```makefile
local-chat:
	scripts/local-chat-scenario
```

`scripts/local-chat-scenario` invoca `local-chat` em sequência com os passos do roteiro. Extraído para script separado conforme CLAUDE.md §15.

## Fora de escopo

- CLI completa (`waspctl`). Este spec entrega o script provisório e a base de endpoints; a CLI é um wrapper futuro sobre o mesmo HTTP.
- Asserts sobre conteúdo do LLM no `make local-chat` (resposta não-determinística gera falsos positivos).
- Notificadores adicionais (Discord, Slack) — entrarão pelo mesmo padrão de seleção.
- Suporte a `provision.py` rodando contra Gitea local (sem GitHub real). O happy-path do `local-chat` exige a infra do apêndice de `validation.md` (cluster + ArgoCD + Crossplane + GitHub real + `GH_PAT`).
- Auth no endpoint `POST /agents/wasp-agent/runs`. Hoje aceita request sem token em dev local — basta documentar; security review separado.

## Verificação

- Unit: `ConsoleNotifier.send` escreve no logger.
- Unit: `_select_notifier()` cobre os 4 casos (env explícito × token presente).
- Unit: `extract_chat_id` aceita `local:` além de `tg:`.
- E2E pytest: continua passando sem mudanças (RecordingNotifier ainda é o caminho).
- Manual: seguir `docs/runbooks/local-chat.md` com cluster + GitHub reais e ver o `[NOTIFIER ...]` no terminal do `make run` quando `Platform.Ready=True`.

## Próximo passo

Promover a Approved após review. Plano de implementação separado em `sdlc/03-execution/`.
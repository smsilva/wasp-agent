# CLAUDE.md

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 5. TDD

We are passionate about testing. We write tests for every feature, bug fix, and refactor. Tests are the safety net that allows us to move fast without breaking things.

The code coverage threshold is 100%. Use `pytest --cov` (`pytest-cov` + `coverage.py`) to verify coverage.

## 6. Code

This project uses primarily Python. For formatting code, use `ruff`.

For dependencies we use `uv`.

## 7. Documentation structure (`docs/`)

Single source of current state: `HANDOFF.md` at the repo root.

Flow for new features: **exploration → design → execution**.

Each SDLC subfolder uses an `archived/` subdirectory for completed/superseded items, same pattern as `docs/security/issues/archived/` (see §9).

| Folder | Answers | Content | Archive when |
|---|---|---|---|
| `sdlc/01-exploration/` | *What and why?* | Problem context, alternatives, technical spikes | Exploration led to a design |
| `sdlc/02-design/` | *How will it look?* | Solution spec: architecture, interfaces, expected behavior | Implementation merged to `main` |
| `sdlc/03-execution/` | *How will we build it?* | Step-by-step plan: tasks, order, dependencies, verification criteria | Implementation merged to `main` |
| `architecture/` | Living docs about the current system | `<topic>.md` | Never — update in place |
| `references/` | Living docs about external tools/APIs | `<topic>.md` | Never — update in place |
| `runbooks/` | Manual procedures (setup, troubleshooting) | `<topic>.md` | Never — update in place |
| `security/issues/` | Security findings (see §9) | `SEC-NNN-<slug>.md` | Resolved (per §9) |

**Spec `Status` field** (header, right after `**Date:**`):

| Status | Meaning |
|---|---|
| `Idea` | Problem statement only; not designed yet |
| `Draft` | Design in progress |
| `Approved` | Ready to plan and implement |
| `Implemented` | Merged to `main` — archive the file |
| `Deferred` | Postponed or superseded by another spec |

Lightweight reminders (one line, no context) belong in the **Backlog** section of `HANDOFF.md`, not in `sdlc/02-design/`.

**Header block formatting:** when stacking multiple `**Field:**` lines without blank lines between them (e.g., `**Date:**`, `**Status:**`, `**Scope:**`), end each line with **two trailing spaces** so Markdown renders a line break instead of collapsing them onto one line.

## 8. agno

See `docs/references/agno.md`.

## 9. Security

- **Autenticação/autorização de usuários**: implementado via allowlist multi-canal (`auth_users`). Ver `docs/runbooks/auth-admin.md`.
- **Security review**: pendente — cobrir autorizações, inputs não sanitizados, exposição de tokens.

## 9a. Security tracking

Active security issues live in `docs/security/issues/SEC-NNN-<slug>.md`.
When resolved, move to `docs/security/issues/archived/`.

Each file has: `id`, `severity`, `status`, `opened` (and `resolved` when archived), description, impact, and fix.

When doing a security review, check open issues before reporting duplicates.

## 10. ruff / lint

- `# noqa: E402` on imports after `load_dotenv()` in `main.py` — intentional violation (env vars must be loaded before agno imports).
- `# noqa: F401` on `import main` inside test functions — side-effect import (runs module code).
- `ruff check .` must pass clean. Run before every commit.

## 11. Platform provisioning

See `docs/architecture/platform-provisioning.md`.

## 12. Telegram — bot tone

In the system prompt, include explicit anti-pattern instructions to control LLM tone:
- No filler words ("Sure!", "Perfect!", "Excellent!")
- No emojis, no exclamation marks
- Short paragraphs separated by blank lines
- Avoid bullet lists and bold except when structure genuinely helps
- When relaying a successful tool result, use the `message` field from the dict — do not invent additional text

## 12a. Telegram router wrapping — prefixo `/telegram`

agno cria o `APIRouter` com `prefix="/telegram"`. Rotas decoradas com `@router.post("/webhook", ...)` aparecem em `router.routes` com `path="/telegram/webhook"`, **não** `"/webhook"`. Ao inspecionar/wrap as rotas em `main.py`, casar por suffix (`r.path.endswith("/webhook")`) ou por `r.name == "telegram_webhook"`, nunca por equivalência exata. Unit tests com `MagicMock(path="/webhook")` passam mesmo contra implementação quebrada — incluir pelo menos um teste com path prefixado.

**Type annotations obrigatórias no wrapper:** a função de substituição (`webhook_with_auth`) **deve** ter `request: Request` e `background_tasks: BackgroundTasks` anotados. Sem anotações, FastAPI tenta resolvê-los como query params e retorna 422 em todo POST do Telegram. Importar `Request` de `starlette.requests` e `BackgroundTasks` de `starlette.background` dentro de `get_router_with_auth` (não no topo do módulo) para que estejam no escopo na definição da função. Regressão coberta por `test_webhook_with_auth_has_fastapi_type_annotations` via `inspect.signature` — testes que chamam o endpoint diretamente não capturam esse bug.

## 13. Async watcher

See `docs/architecture/async-watcher.md`.

## 15. Makefile

When a Makefile target needs more than a single command, extract the commands to a bash script in `scripts/` and call the script from the target.

## 14. Notifier abstraction

`wasp/notifier.py` defines `Notifier` (Protocol), `TelegramNotifier`, and `RecordingNotifier`. `watch_platform` is channel-agnostic — it receives a `Notifier` instance. When adding a new channel (Discord, Slack, WhatsApp), add a new `Notifier` implementation in `wasp/notifier.py` and inject it from `provision.py`; never add channel-specific logic to `watcher.py`.

Notifier selection routes by **channel of origin**, not global env: `_select_notifier(channel)` reads the `session_id` prefix (`tg`, `local`, ...) via `extract_channel`. `WASP_AGENT_NOTIFIER` env var still overrides when explicitly set. Required because multiple channels can coexist (e.g. Telegram bot + local-chat) — selecting by env alone sends notifications to the wrong channel and silently fails.

## 17. Variáveis de ambiente com prefixo WASP_AGENT_

Variáveis que configuram o comportamento do agent usam o prefixo `WASP_AGENT_` (ex.: `WASP_AGENT_NOTIFIER`). Ao adicionar nova variável de configuração do agent, seguir esse padrão.

## 18. Testes e OTEL_EXPORTER_OTLP_ENDPOINT

O fixture `mock_agno` em `tests/conftest.py` mocka `agno.models` como `MagicMock`. Se `OTEL_EXPORTER_OTLP_ENDPOINT` estiver setado no shell, `configure()` chama `AgnoInstrumentor`, que tenta `from agno.models.base import Model` e falha contra o mock. O fixture já faz `monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)` para isolar os testes — não remover essa linha.

O loop de `sys.modules.pop` no fixture deve incluir todo `wasp.*` module criado. Ao adicionar um novo módulo em `wasp/`, incluí-lo na lista do fixture; caso contrário, estado do módulo vaza entre testes e causa falhas intermitentes.

## 20. Logging — `wasp/logging.py`

`chat_id_var` é um `ContextVar` definido em `wasp/logging.py`. Python's `threading.Thread` **não herda** ContextVar do thread pai — cada thread começa com contexto vazio. `watch_platform` roda em thread separado e chama `chat_id_var.set(chat_id)` explicitamente no início; qualquer função futura que rode em thread novo e precise de `chat_id` deve fazer o mesmo.

## 19. E2E fixture — patch `_select_notifier`, não `TelegramNotifier`

Em `tests/e2e/conftest.py`, o `agent_client` patcheia `_select_notifier` diretamente para retornar o `recording_notifier`:

```python
monkeypatch.setattr(wasp.provision, "_select_notifier", lambda *a, **kw: recording_notifier)
```

Patchear só `TelegramNotifier` não funciona: `WASP_AGENT_NOTIFIER=console` no `.env` é carregado pelo `load_dotenv()` em `main.py` no import, e `_select_notifier` retorna `ConsoleNotifier` antes de chegar na chamada de `TelegramNotifier`. O notifier vai para o console e o `RecordingNotifier` nunca recebe — teste falha com `TimeoutError` sem mensagem de erro clara.

O mesmo fixture também monkeypatcha `wasp.auth.is_authorized` para retornar um `user_id` fake:

```python
monkeypatch.setattr(wasp.auth, "is_authorized", lambda channel, channel_id: "e2e-user")
```

Sem isso, o `session_id="tg:..."` usado no teste cai no auth guard de `provision_platform_instance` e retorna `{"status": "unauthorized"}` silenciosamente — o teste falha lá embaixo no `get_file()` do Gitea com 404, mascarando a causa real.

## 16. Validação

**Ao fim de todo ciclo de desenvolvimento (antes de declarar a feature pronta, abrir PR ou fazer merge), rodar obrigatoriamente:**

```bash
make test
make e2e-with-debug
```

Os dois são complementares e não substituíveis:

- `make test` roda a suite unitária com `mock_agno` — agno é mockado, então bugs na integração real (ex.: router do `Telegram` com prefixo `/telegram`, comportamento de `agno.os.AgentOS` em `import main`) **não aparecem aqui**.
- `make e2e-with-debug` importa `main.py` real, sobe Gitea + k3d + `fake_reconciler`, e executa o fluxo completo turn-1/turn-2/watcher/notificação. É onde bugs como `webhook_route = next(... path == "/webhook")` quebrando contra o prefixo real do agno aparecem.

Não pular o e2e por ser mais lento. Lição registrada (2026-05-23): o fix do `/telegram/webhook` prefix só foi descoberto ao rodar `make e2e-with-debug` depois de `make test` verde — a suite unitária usava `MagicMock(path="/webhook")` e nunca exercitou o router real.

### Caminhos

Quatro caminhos distintos — ver índice em `docs/runbooks/validation.md`.

- **`make e2e`** — pipeline automatizado. Usa `make k3d-up` (k3d barebones + CRD `Platform`), `fake_reconciler`, Gitea container, `RecordingNotifier`. Sem Telegram, sem cluster GitOps real.
- **Smoke test Telegram (manual)** — `make run` + ngrok + webhook (`docs/runbooks/telegram-local-dev.md`). Valida canal Telegram + comportamento do LLM (confirmação, memória de sessão). **Não exige cluster.**
- **Prometheus** — `make smoke-prometheus` (standalone) ou `PROMETHEUS_METRICS_ACTIVE=true make run` + `curl /telemetry/prometheus` (integrado). Independe dos dois acima.

Para validar o ciclo GitOps real (raro — mudanças em `wasp/provision.py`, `wasp/watcher.py` ou na Composition), subir cluster com `make gitops-up` (cluster `k3s-default`, distinto do `wasp-local` do `make k3d-up`) e derrubar com `make gitops-down`. Detalhes em `docs/runbooks/k3d-argocd-wasp-gitops.md`. Isso é validação pesada, não smoke test.
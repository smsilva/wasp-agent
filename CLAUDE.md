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

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 5. TDD

We are passionate about testing. We write tests for every feature, bug fix, and refactor. Tests are the safety net that allows us to move fast without breaking things.

The code coverage threshold is 100%. Use `pytest --cov` (`pytest-cov` + `coverage.py`) to verify coverage.

## 6. Code

This project uses primarily Python. For formatting code, use `ruff`.

For dependencies we use `uv`.

## 7. Brainstorming and specification

Flow: brainstorm → spec → plan

All files stored in `docs/`, named `<YYYY-MM-DD>-<topic>.md`:
1. `brainstorms/` — session context, decisions, alternatives
2. `specs/` — approved design (what to build)
3. `plans/` — implementation plan (how to build, step-by-step)

## 8. agno

- Versão mínima: `agno>=2.0.0`. A API 1.x é diferente e incompatível.
- Sessão SQLite: `db=SqliteDb(db_file=..., session_table=...)` via `agno.db.sqlite.sqlite`. Não existe `SqliteAgentStorage`.
- Histórico de contexto: `add_history_to_context=True` (não `add_history_to_messages`).
- `SqliteDb` requer `sqlalchemy` — declare como dependência explícita no projeto.
- Antes de escrever código com agno, verifique os caminhos de import no pacote instalado (`.venv/lib/`). A documentação oficial frequentemente diverge da versão instalada.

- `@tool(requires_confirmation=True)` em `tools/provision.py`: ao adicionar um módulo com esse decorator, adicionar `"agno.tools"` a `AGNO_MODULES` em `conftest.py` e configurar `mocks["agno.tools"].tool = lambda **kwargs: lambda fn: fn` — isso mantém a função diretamente chamável nos testes. Também fazer `sys.modules.pop("tools", None)` e `sys.modules.pop("tools.provision", None)` no setup e teardown do fixture; sem isso, o decorator corre com o mock errado na primeira importação e quebra os testes subsequentes.

Para detalhes e checklist de ciclos futuros, ver `docs/notes/2026-05-13-agno-api-cycle1.md`.

Para rodar o bot localmente com ngrok, ver `docs/runbooks/telegram-local-dev.md`.

## 9. Security tracking

Issues de segurança ativas ficam em `docs/security/issues/SEC-NNN-<slug>.md`.
Quando resolvida, mover para `docs/security/issues/archived/`.

Cada arquivo tem: `id`, `severity`, `status`, `opened` (e `resolved` quando arquivada), descrição, impacto e fix.

Ao fazer security review, checar issues abertas antes de reportar duplicatas.

## 11. Platform provisioning

- GitOps repo: `smsilva/wasp-gitops`, branch `dev`, path `infrastructure/tenants/{name}.yaml`.
- CRD: `apiVersion: wasp.silvios.me/v1alpha1`, `kind: Platform`. Campo `name` é top-level (não em `metadata`).
- Endpoint derivado deterministicamente: `gateway.{aws-region}.{name}.{domain}` — nenhum campo desconhecido no momento do commit.
- Services são fixos para toda instância: auth, discovery, callback, portal.
- Default domain: `wasp.silvios.me`. Default region: `us-east-1`.
- Use Pydantic models para gerar o manifesto (não Jinja2). O LLM extrai parâmetros; Pydantic valida e serializa. Nunca peça pro LLM gerar YAML Crossplane diretamente.
- Tools de provisionamento usam `@tool(requires_confirmation=True)` para exigir confirmação antes de commitar.
- Sempre usar `yaml.safe_dump()` (não `yaml.dump()`) ao serializar manifests — impede que input do LLM/usuário injete objetos Python arbitrários no YAML.
- Parâmetros `list` com default em tool functions: usar tupla como constante (`DEFAULT_REGIONS = ("us-east-1",)`) e `None` na assinatura com inicialização no corpo (`regions = list(DEFAULT_REGIONS)`). Lista mutável como default é Python gotcha.
- Sanitizar strings de usuário antes de interpolar em mensagens de commit: `value.replace("\n", " ").replace("\r", " ")` — evita injeção de linhas extras no commit message.

Para o design completo do ciclo 2, ver `docs/specs/2026-05-15-platform-provisioning-design.md`.

## 10. ruff / lint

- `# noqa: E402` nos imports após `load_dotenv()` em `main.py` — violação intencional (env vars devem estar carregadas antes dos imports do agno).
- `# noqa: F401` em `import main` dentro de funções de teste — import por efeito colateral (executa código de módulo).
- `ruff check .` deve passar limpo. Rode antes de qualquer commit.

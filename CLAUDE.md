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

Para detalhes e checklist de ciclos futuros, ver `docs/notes/2026-05-13-agno-api-cycle1.md`.

## 9. ruff / lint

- `# noqa: E402` nos imports após `load_dotenv()` em `main.py` — violação intencional (env vars devem estar carregadas antes dos imports do agno).
- `# noqa: F401` em `import main` dentro de funções de teste — import por efeito colateral (executa código de módulo).
- `ruff check .` deve passar limpo. Rode antes de qualquer commit.

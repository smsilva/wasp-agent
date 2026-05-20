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

## 9. Security — próximos passos

- **Autenticação/autorização de usuários**: implementar mecanismo para limitar quais usuários podem usar o bot (allowlist de `chat_id`, por exemplo).
- **Security review**: realizar após implementar autenticação — cobrir autorizações, inputs não sanitizados, exposição de tokens.

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

## 13. Async watcher

See `docs/architecture/async-watcher.md`.

## 14. Notifier abstraction

`tools/notifier.py` defines `Notifier` (Protocol), `TelegramNotifier`, and `RecordingNotifier`. `watch_platform` is channel-agnostic — it receives a `Notifier` instance. When adding a new channel (Discord, Slack, WhatsApp), add a new `Notifier` implementation in `tools/notifier.py` and inject it from `provision.py`; never add channel-specific logic to `watcher.py`.
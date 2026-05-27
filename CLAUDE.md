# CLAUDE.md

## Principles

**Think first.** State assumptions explicitly. If multiple interpretations exist, present them. If uncertain, ask before implementing.

**Simplicity.** Minimum code that solves the problem. No abstractions for single-use code, no flexibility that wasn't requested, no error handling for impossible scenarios. If 200 lines could be 50, rewrite it.

**Surgical changes.** Touch only what the task requires. Don't refactor adjacent code, reformat, or delete pre-existing dead code (mention it instead). Only clean up orphans your own changes created. Match existing style.

**Goal-driven.** Transform tasks into verifiable goals with success criteria. State a brief plan for multi-step tasks. Loop until verified.

## Code

- Python + `ruff` for formatting + `uv` for dependencies.
- 100% coverage required. Verify with `pytest --cov`.
- `ruff check .` must pass before every commit.

Lint exceptions:
- `# noqa: E402` on imports after `load_dotenv()` in `main.py` (env vars must precede agno imports).
- `# noqa: F401` on `import main` inside test functions (side-effect import).

## Validation (mandatory before PR/merge)

```bash
make format
make test
make e2e-with-debug
```

- `make test` mocks agno via `mock_agno` fixture — won't catch real integration bugs.
- `make e2e-with-debug` imports real `main.py`, runs Gitea + k3d + `fake_reconciler`, exercises full flow.

Don't skip e2e. The `/telegram/webhook` prefix bug (2026-05-23) only surfaced in e2e.

Four validation paths — see `docs/runbooks/validation.md`.

## Project structure

### Documentation (`docs/`)

Single source of current state: `HANDOFF.md` at repo root.

Flow for new features: **exploration/ → design/ → execution/**. Each SDLC subfolder uses `archived/` for completed/superseded items.

| Folder | Answers | Content | Archive when |
|---|---|---|---|
| `sdlc/01-exploration/` | *What and why?* | Problem context, alternatives, technical spikes | Exploration led to a design |
| `sdlc/02-design/` | *How will it look?* | Solution spec: architecture, interfaces, expected behavior | Implementation merged to `main` |
| `sdlc/03-execution/` | *How will we build it?* | Step-by-step plan: tasks, order, dependencies, verification criteria | Implementation merged to `main` |
| `architecture/` | Living docs about current system | `<topic>.md` | Never — update in place |
| `references/` | Living docs about external tools/APIs | `<topic>.md` | Never — update in place |
| `runbooks/` | Manual procedures (setup, troubleshooting) | `<topic>.md` | Never — update in place |
| `security/issues/` | Security findings | `SEC-NNN-<slug>.md` | Resolved |

Spec `Status` values: `Idea`, `Draft`, `Approved`, `Implemented`, `Deferred`.

One-line reminders without context go in `HANDOFF.md` **Backlog**, not `sdlc/02-design/`.

Markdown header blocks: when stacking `**Field:**` lines without blank lines between them, end each with **two trailing spaces** so they render as separate lines.

### Packages — `wasp/clients/`

Channel-specific code lives in `wasp/clients/<channel>/`:

```
wasp/clients/
  __init__.py          ← Notifier Protocol only
  telegram/            ← see wasp/clients/telegram/CLAUDE.md
  discord/             ← see wasp/clients/discord/CLAUDE.md
  local/
```

Re-exports in `__init__.py` need explicit alias to avoid ruff F401: `from wasp.clients.foo import Bar as Bar`. `RecordingNotifier` (test double) lives in `tests/notifiers.py`, not `wasp/clients/`. New channels (Slack, etc.) follow this layout.

### Packages — `wasp/resources/`

CRD definitions live in `wasp/resources/<kind>/`:

```
wasp/resources/
  base.py              ← ResourceManifest base, MetadataSpec
  platform/
    manifest.py        ← PlatformManifest + group/version/plural constants
    provisioner.py     ← PlatformProvisioner
    inventory.py       ← PlatformInventory + status transformation
```

`wasp/provision.py` is the agent-tools façade — `@tool` wrappers only; logic lives in `wasp/resources/`. Generic Kubernetes API access goes through `wasp/clients/k8s/KubernetesResourceReader.search_for_instance_of(group, version, plural)`.

New CRD (e.g. Cluster): create `wasp/resources/cluster/{manifest,provisioner,inventory}.py`, add `@tool` wrappers in `wasp/provision.py`.

### Makefile

When a target needs more than one command, extract to `scripts/<name>` and call it from the target.

### Startup (`wasp/startup.py`)

Contains `startup()`: `configure_logging()`, `GitOpsCommitter.probe()`, `os.umask(0o077)`. Called from `main.py` after `load_dotenv()`.

`load_dotenv()` stays in `main.py` (not `startup()`) because any `import wasp.*` triggers `wasp/__init__.py` → `wasp.provision` → `wasp.telemetry.configure()` at import time. `.env` vars (`OTEL_EXPORTER_OTLP_ENDPOINT`, `PROMETHEUS_METRICS_ACTIVE`) must be loaded before that.

## Conventions

### Env vars

Agent configuration uses prefix `WASP_AGENT_` (e.g., `WASP_AGENT_NOTIFIER`).

### Bot tone

System prompt must include explicit anti-pattern instructions:
- No filler ("Sure!", "Perfect!", "Excellent!")
- No emojis, no exclamation marks
- Short paragraphs separated by blank lines
- Avoid bullet lists and bold except when structure genuinely helps
- When relaying a tool result, use its `message` field verbatim — don't invent text

### Notifier abstraction

`wasp/clients/__init__.py` defines the `Notifier` Protocol. `watch_platform` is channel-agnostic — receives a `Notifier` instance. Never put channel-specific logic in `watcher.py`.

`_select_notifier(channel)` routes by channel of origin (parsed from `session_id` prefix via `extract_channel`), not global env. `WASP_AGENT_NOTIFIER` overrides when set.

### ContextVar not inherited by threads

`chat_id_var` is a `ContextVar` in `wasp/logging.py`. `threading.Thread` does **not** inherit ContextVar — each thread starts with empty context. `watch_platform` explicitly calls `chat_id_var.set(chat_id)` at the start. Any future code running in a new thread that needs `chat_id` must do the same.

### SQLite atomic check-then-write (`wasp/auth.py`)

Check-then-write operations call `con.execute("BEGIN IMMEDIATE")` before the first SELECT to acquire the write lock immediately. The subsequent `with con:` commits (success) or rolls back (exception). Early `return None` before `with con:` triggers a rollback of an empty transaction — no side effects.

## Security

- User auth/authz via multi-channel allowlist. See `docs/runbooks/auth-admin.md`.
- Active issues: `docs/security/issues/SEC-NNN-<slug>.md`. When resolved, move to `archived/`.
- Before reporting a security finding, check open issues for duplicates.

## External references

- agno: `docs/references/agno.md`
- Platform provisioning: `docs/architecture/platform-provisioning.md`
- Async watcher: `docs/architecture/async-watcher.md`
- Tests gotchas: `tests/CLAUDE.md`
- Telegram integration: `wasp/clients/telegram/CLAUDE.md`
- Discord integration: `wasp/clients/discord/CLAUDE.md`

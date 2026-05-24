# wasp-agent

DevOps assistant that provisions infrastructure via chat. Engineers send messages on Telegram; the agent commits Crossplane manifests to a GitOps repo and sends a proactive notification when the resource is ready.

## Architecture

```
Telegram → agno Agent → provision_platform_instance tool → GitHub (wasp-gitops)
                                                          → ArgoCD → Crossplane
                     ← async watcher ← Crossplane status polling
```

- **Agent**: [agno](https://github.com/agno-agi/agno) with Claude (Bedrock) and SQLite session memory
- **Provisioning**: commits a `Platform` CRD manifest to `smsilva/wasp-gitops`; ArgoCD reconciles
- **Watcher**: background thread polls Crossplane status and notifies the originating Telegram chat
- **Observability**: OpenTelemetry traces (OTLP) + Prometheus metrics

## Setup

```bash
cp .env.example .env
# fill in ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, TELEGRAM_TOKEN,
# TELEGRAM_BOT_URL, TELEGRAM_WEBHOOK_SECRET_TOKEN, GH_PAT
uv sync
```

See `docs/runbooks/` for GitHub PAT setup and other procedures.

## Validation

| Caminho | Quando usar | Runbook |
|---|---|---|
| E2E automatizado | Após qualquer mudança de código | [`docs/runbooks/validation-e2e.md`](docs/runbooks/validation-e2e.md) |
| Smoke test Telegram | Canal Telegram, auth, comportamento do LLM | [`docs/runbooks/validation-telegram.md`](docs/runbooks/validation-telegram.md) |
| Prometheus | Métricas e instrumentação | [`docs/runbooks/validation-prometheus.md`](docs/runbooks/validation-prometheus.md) |
| Local chat | Iteração rápida sem Telegram | [`docs/runbooks/validation-local-chat.md`](docs/runbooks/validation-local-chat.md) |
| Ciclo GitOps completo | Mudanças em `provision.py`, `watcher.py` ou Composition | [`docs/runbooks/validation-gitops.md`](docs/runbooks/validation-gitops.md) |

## Usage

```bash
make run     # start the agent
make test    # run tests with coverage
make smoke   # validate OTel spans against local Jaeger
```

Jaeger for local tracing:

```bash
docker compose up -d
```

## SDLC

Flow: **exploration → design → execution**.

| Folder | Answers | Content |
|---|---|---|
| `docs/sdlc/01-exploration/` | *What and why?* | Problem context, alternatives, technical spikes |
| `docs/sdlc/02-design/` | *How will it look?* | Solution spec: architecture, interfaces, expected behavior |
| `docs/sdlc/03-execution/` | *How will we build it?* | Step-by-step plan: tasks, order, dependencies, verification criteria |

Completed items move to `archived/` inside each folder. Current state: `HANDOFF.md`.

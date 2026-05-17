# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–3 completos e em `main`. A próxima feature em andamento é **OpenTelemetry** (Ciclo 4) — spec aprovado, aguardando plano de implementação.

## Current Progress

**Ciclos 1, 2 e 3 completos em `main`.** Smoke test end-to-end validado em 2026-05-16. Loop completo (Telegram → GitHub commit → ArgoCD sync → Crossplane reconcile → watcher detecta Ready → notificação Telegram) fecha em < 1 min.

### Esta sessão (2026-05-17)

- Tenants de teste (`sandbox-1`, `producao`) removidos do `wasp-gitops` — `5690ae2`.
- System prompt reforçado: `"Pronto!"` adicionado à lista de filler words; ArgoCD/Crossplane/GitHub/Kubernetes explicitamente proibidos nas respostas do bot — `d80f994`.
- Lint limpo (F401, E402 preexistentes corrigidos em test files e provision.py).
- `dev` mergeado em `main` — `7b6518d`.
- Spec OTel escrito e commitado em `docs/superpowers/specs/2026-05-17-opentelemetry-design.md` — `e530d61`.
- Aprendizados sobre decorator order com `@tool` e limitações de hooks do agno adicionados em `docs/references/agno.md` — `045cc0b`.

### Estado dos ciclos

- **Ciclo 1** — mergeado em `main`. Agent + Telegram interface + SQLite.
- **Ciclo 2** — mergeado em `main`. `provision_platform_instance` tool + Pydantic models + commit GitOps.
- **Ciclo 3** — mergeado em `main`. Watcher async, polling de Platform CR, notificação Telegram.
- **Ciclo 4 (OTel)** — spec aprovado. Plano de implementação ainda não criado.

## What Worked

- Spec OTel usa `@instrument` como decorator interno ao `@tool` (agno exige que `@tool` seja o externo para que `inspect.signature()` via `__wrapped__` funcione corretamente).
- Métricas channel-agnósticas: label `channel` com valores `tg`/`discord`/etc., derivado do prefixo de `session_id` — não menciona Telegram no código de métricas.
- Watcher como trace separado com `SpanLink` para o span pai — padrão OTel correto para trabalho fire-and-forget em thread daemon.
- Configuração 100% via env vars OTel padrão (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`); no-op automático quando ausentes.

## What Didn't Work

- Starlette middleware para root span `agent.message.handle`: agno não expõe pre-routing hook com `session_id`. O `channel`/`user_id` só está disponível dentro da tool via `run_context`. Mensagens sem tool call ficam sem trace nesta versão (gap aceito).

## Next Steps

1. **Usuário revisa o spec OTel** — `docs/superpowers/specs/2026-05-17-opentelemetry-design.md`. Confirmar se o design está ok antes de criar o plano.
2. **Criar plano de implementação** — invocar `writing-plans` skill com o spec aprovado.
3. **Implementar Ciclo 4 (OTel)** — `telemetry.py`, instrumentação de `provision.py` e `watcher.py`, rota `/metrics`, testes.
4. **Merge `dev` → `main`** após testes passando e cobertura 100%.

### Backlog (depois do OTel)

- **Restart resilience do watcher** — persistir `platform_watches` em SQLite. Spec: `docs/specs/2026-05-16-platform-watcher-restart-resilience.md`.
- **Logging estruturado** — JSONL opcional via `LOG_FILE`. Será consolidado com OTel logs no Ciclo 4. Spec: `docs/specs/2026-05-16-structured-logging.md`.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.

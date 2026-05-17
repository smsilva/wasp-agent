# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–3 completos em `main`. Próxima feature: **OpenTelemetry (Ciclo 4)** — spec aprovado em `dev`, aguardando plano de implementação.

## Current Progress

**Ciclos 1, 2 e 3 em `main`.** Smoke test end-to-end validado em 2026-05-16 (Telegram → GitHub → ArgoCD → Crossplane → watcher → notificação). Loop fecha em < 1 min.

### Esta sessão (2026-05-17)

- **Reorganização de `docs/`** — `39f0870`:
  - Pasta órfã `docs/superpowers/` removida; OTel spec movido para `docs/specs/`
  - `docs/notes/` eliminado (conteúdo já em `docs/references/agno.md`)
  - Criados `archived/` em `specs/`, `plans/`, `brainstorms/` (mesmo padrão de `security/issues/archived/`)
  - 8 arquivos dos Ciclos 1-3 movidos para `archived/`
  - `**Status:**` padronizado em todos os 6 specs (`Idea | Draft | Approved | Implemented | Deferred`)
  - `CLAUDE.md §7` reescrito com tabela de subpastas + taxonomia de Status + regra de arquivamento
- **Convenção de quebra de linha em headers** — `452ca56`: dois espaços no fim de linhas `**Field:**` empilhadas (renderiza line break em vez de colapsar).
- **Skill global `handoff` atualizada** — em `~/git/linux/ac38862`: enumera `docs/specs/*.md` e `docs/plans/*.md` ativos (não-archived) e usa para popular **Next Steps**.

### Commits no `dev` ainda não em `main`

```
452ca56 docs: note two-space line break for stacked header fields
39f0870 docs: reorganize docs/ with archived/ convention and Status field
42592ab docs: update HANDOFF.md — OTel spec done, awaiting review and plan
045cc0b docs(agno): add OTel decorator order and pre-routing hook gotchas
e530d61 docs(specs): add OpenTelemetry instrumentation design
```

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/specs/2026-05-17-opentelemetry-design.md` | Approved (sem plano ainda) |
| `docs/specs/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/specs/2026-05-16-structured-logging.md` | Deferred (será absorvido pelo OTel) |

### Plans ativos

| Arquivo | Referência |
|---|---|
| `docs/plans/2026-05-17-opentelemetry-cycle4.md` | Implementa o spec OTel |

## What Worked

- Estender o padrão `archived/` (que já existia para security) para `specs/`, `plans/` e `brainstorms/` — convenção uniforme, fácil de manter.
- Campo `**Status:**` no header de cada spec — auto-documenta o que está pronto, em design ou diferido, sem precisar consultar `HANDOFF.md`.
- Skill global `handoff` ficou project-agnostic via guards (`if docs/specs/ exists`) — não quebra projetos sem essa estrutura.

## What Didn't Work

Nada negativo nesta sessão. Reorganização foi puramente mecânica e validada por `git status` em cada etapa.

## Next Steps

1. **Implementar Ciclo 4 (OTel)** — seguir `docs/plans/2026-05-17-opentelemetry-cycle4.md` task a task (TDD). Ordem: deps → `telemetry.py` → `conftest.py` → `provision.py` → `watcher.py` → `main.py`.
2. **Merge `dev` → `main`** após o Ciclo 4 com testes passando e cobertura 100%.

### Backlog

- **Restart resilience do watcher** — persistir `platform_watches` em SQLite. Spec: `docs/specs/2026-05-16-platform-watcher-restart-resilience.md`.
- **Logging estruturado** — JSONL opcional via `LOG_FILE`. Será consolidado com OTel logs no Ciclo 4. Spec: `docs/specs/2026-05-16-structured-logging.md`.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.

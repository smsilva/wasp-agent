# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

Ciclos 1–5 completos e em `main`.

## Current Progress

**Ciclos 1–5 em `main`.** Smoke test end-to-end do Ciclo 4 validado em 2026-05-17 (Telegram → GitHub → ArgoCD → Crossplane → watcher → notificação proativa). Ciclo 5 validado em 2026-05-19 com `make smoke` (spans AGENT + LLM chegando ao Jaeger).

### Esta sessão (2026-05-19)

- **Grilling session** para fechar decisões de design do pipeline E2E (10 perguntas, todas resolvidas)
- **Spec aprovado** (`docs/sdlc/02-design/2026-05-19-e2e-testing-pipeline.md`): k3d + Gitea + fake reconciler + `RecordingNotifier` + in-process agent
- **Plano de execução** (`docs/sdlc/03-execution/2026-05-19-e2e-testing-pipeline.md`): 5 passos, passos 1–2 concluídos
- **Passo 1 — `Notifier` protocol** (`d8441f7`):
  - `tools/notifier.py`: `Notifier` Protocol, `TelegramNotifier(token, base_url)`, `RecordingNotifier`
  - `tools/watcher.py`: `watch_platform` recebe `notifier: Notifier` em vez de `token`; `notify_telegram` removido
  - `tools/provision.py`: injeta `TelegramNotifier(token=token)` ao spawnar watcher
  - 52 testes, 100% cobertura, ruff clean
- **Passo 2 — Configurabilidade git** (`d8441f7`):
  - `GITHUB_BASE_URL` e `GITOPS_REPO` como env vars em `provision.py`
  - `Github(login_or_token=pat, base_url=github_base_url).get_repo(gitops_repo)`
  - Habilita apontar para Gitea local nos testes E2E

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-19-e2e-testing-pipeline.md` | Approved — plano em andamento |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/sdlc/02-design/2026-05-16-structured-logging.md` | Deferred (avaliar consolidação com OTel logs) |

### Plans ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/03-execution/2026-05-19-e2e-testing-pipeline.md` | In Progress — passos 1–2 feitos, 3–5 pendentes |

## What Worked

- **Grilling antes do spec**: fechar todas as decisões de design antes de escrever código eliminou retrabalho
- **Notifier Protocol**: desacopla o watcher do canal desde o início; `RecordingNotifier` torna os testes limpos sem mocks
- **TDD via subagent** para Ciclos 4 e 5: cobertura 100% mantida desde o início, ruff clean a cada commit
- **`SpanLink`** para correlacionar trabalho assíncrono do watcher ao span síncrono da tool — padrão OTel correto para fire-and-forget
- **`make smoke` + Jaeger** — validação E2E de spans sem precisar de infraestrutura permanente

## What Didn't Work

- **Rota `/metrics`**: agno reserva esse path. Movido para `/telemetry/prometheus`
- **Default logging WARNING** escondeu logs do watcher na primeira execução do smoke test
- **Suposição errada sobre `session_id`**: agno 2.0+ adiciona suffix de message hash (4 partes, não 3)
- **Tentativa de suprimir DeprecationWarning** com `-W ignore` — hábito perigoso. Persistido em `feedback-no-suppressing-warnings.md`

## Next Steps

### Em andamento — continuar execução

**Pipeline E2E** (`docs/sdlc/03-execution/2026-05-19-e2e-testing-pipeline.md`) — passos restantes:

3. **Fixtures E2E** (`tests/e2e/conftest.py`): `k3d_cluster` (cria cluster + instala CRDs), `gitea_container` (sobe Gitea via docker, cria repo `wasp-gitops`), `fake_reconciler` (thread que faz kubectl patch status Ready após 3s), `agent_client` (`httpx.AsyncClient(app=app)` com `RecordingNotifier` injetado)
4. **Teste E2E** (`tests/e2e/test_full_provisioning_flow.py`): multi-turn real, valida commit no Gitea, valida notifier, valida métricas Prometheus
5. **CI** (`.github/workflows/e2e.yml`): trigger em PRs para `dev`, `pytest -m e2e --no-cov`

Também necessário antes do passo 3: adicionar `@pytest.mark.e2e` ao `pyproject.toml` e `tests/e2e/*` ao `omit` do coverage.

### Brainstorms abertos

- `docs/sdlc/01-exploration/2026-05-17-e2e-testing-without-external-chats.md` — supersedido pelo spec aprovado; pode ser arquivado

### Backlog

- **Structured logging completo** (`docs/sdlc/02-design/2026-05-16-structured-logging.md`) — JSONL via `LOG_FILE`, `OTLPLogExporter` integration. Avaliar consolidação com OTel logs do Ciclo 5.
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`) — persistir `platform_watches` em SQLite para sobreviver a restarts.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.

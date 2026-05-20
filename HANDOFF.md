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
  - 53 testes, 100% cobertura, ruff clean
- **Passo 2 — Configurabilidade git** (`d8441f7`):
  - `GITHUB_BASE_URL` e `GITOPS_REPO` como env vars em `provision.py`
  - `Github(login_or_token=pat, base_url=github_base_url).get_repo(gitops_repo)`
  - Habilita apontar para Gitea local nos testes E2E
- **GitClient abstraction** (`tools/git_client.py`):
  - `GitClient` Protocol + `PyGithubClient` (GitHub) + `GiteaClient` (Gitea via httpx direto)
  - `provision.py` deixa de usar `github.Github` diretamente; instancia `PyGithubClient`
  - E2E injeta `GiteaClient` via monkeypatch — padrão simétrico ao `TelegramNotifier`/`RecordingNotifier`
  - Motivo: PyGithub é incompatível com Gitea 1.22 (assertion de porta + PUT vs POST). Ver `docs/references/gitea.md`
  - 57 testes (4 novos em `tests/test_git_client.py`), 100% cobertura, ruff clean

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-19-e2e-testing-pipeline.md` | Approved — plano em andamento |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |
| `docs/sdlc/02-design/2026-05-16-structured-logging.md` | Deferred (avaliar consolidação com OTel logs) |

### Plans ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/03-execution/2026-05-19-e2e-testing-pipeline.md` | Implemented — passos 1–5 concluídos; CI pendente de AWS OIDC |

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

### Em andamento — destravar E2E (`test_provision_and_notify`)

**Status atual da execução local (2026-05-19):**
- Infra E2E roda inteira sem erro: k3d cria cluster, CRD `Platform` aplicada, Gitea sobe na 3456, agente responde via SSE in-process, tool `provision_platform_instance` executa, `GiteaClient` é instanciado via monkeypatch.
- O teste falha no `assert "confirma" in content1.lower()` (linha 34) **porque o LLM (Claude Haiku 4.5) ignora a instrução `"Always confirm resource creation or deletion before executing."` em `main.py:34`** e chama a tool já no turno 1. A resposta no turno 1 é literalmente o `message` de `provision.py` em status=provisioning — ou seja, o caminho de produção funcionou, só não houve a confirmação prévia.

**Decisão pendente entre três caminhos:**
1. **A. Reforçar system prompt** (recomendado) — instrução explícita "Never call provision_platform_instance on the first user turn. Always ask 'Confirma?' first and wait for an affirmative reply." Muda produção, ainda depende do LLM.
2. **B. Ajustar o teste** — aceitar o fluxo em uma ou duas turns; validar diretamente commit no Gitea + notificação. Não muda produção.
3. **C. Trocar Haiku por Sonnet só no E2E** — mais lento e caro por execução.

**Pré-requisito de execução local:** `set -a; source .env; set +a; uv run pytest tests/e2e/ -m e2e --no-cov -v` — exige `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` (llmproxy), docker e k3d. Limpar leftovers se houver: `docker rm -f wasp-e2e-gitea; k3d cluster delete wasp-e2e`.

### Pipeline E2E — CI

Workflow `.github/workflows/e2e.yaml` pronto e passa em pre-flight. Pendente: validação em PR real para `dev` (independe do bloqueio acima, já que CI usa o mesmo modelo via secrets).

### Brainstorms abertos

- `docs/sdlc/01-exploration/2026-05-17-e2e-testing-without-external-chats.md` — supersedido pelo spec aprovado; pode ser arquivado

### Backlog

- **Structured logging completo** (`docs/sdlc/02-design/2026-05-16-structured-logging.md`) — JSONL via `LOG_FILE`, `OTLPLogExporter` integration. Avaliar consolidação com OTel logs do Ciclo 5.
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`) — persistir `platform_watches` em SQLite para sobreviver a restarts.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
- **Makefile `make e2e`** — atalho para o comando E2E local (depende de destravar o teste primeiro).

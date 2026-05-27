# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão, autenticação multi-canal por invite, e suporte futuro a Discord/Slack.

## Current State

`dev` está 11 commits à frente de `main`. `main` tem o código mais completo.

**Entregue nesta sessão (no branch `dev`, ainda não mergeado):**
- Pacote `wasp/resources/` com base genérica `ResourceManifest`/`MetadataSpec` e subpacote `wasp/resources/platform/` (`manifest.py`, `inventory.py`, `provisioner.py`)
- Pacote `wasp/clients/k8s/` com `KubernetesResourceReader.search_for_instance_of(group, version, plural)` genérico + `load_kube_config_auto` (movido de `wasp/watcher.py`)
- `wasp/platform_cluster.py` removido (substituído pelo reader genérico + transformação em `PlatformInventory`)
- `wasp/provision.py` reduzido a 46 linhas: apenas dois `@tool` wrappers (`list_platform_instances`, `provision_platform_instance`)
- Novo comportamento: `provision_platform_instance` cai no `user_id` resolvido pela auth quando `requested_by` vem vazio (não mais commit message com `"Requested by: "` em branco)
- `CLAUDE.md §Packages — wasp/resources/` documenta o padrão `wasp/resources/<crd>/` para o próximo CRD (`Cluster`)
- `CLAUDE.md §Technical notes` adiciona "Mocked exception classes can't be raised or caught" (padrão `FakeConfigException` para testes que usam `mock_agno`)
- Validação: `make format` ✓, `make test` ✓ (234 passed, 100% coverage), `make e2e-with-debug` ✓ (passou na segunda execução — primeira falhou por flakiness do LLM respondendo em inglês em vez de pt-BR)

**Estado anterior** (já em `main`):
- Refatoração `wasp/clients/` por canal (Telegram, local) + `InterfaceLoader` em `wasp/clients/interfaces.py`
- Logging estruturado (`wasp/logging.py`, `JSONFormatter`, `chat_id_var` ContextVar)
- Auth multi-canal (Ciclo 7): `wasp/auth.py`, guard em `provision_platform_instance`, handler `/start <token>`, CLI admin, métrica `wasp_auth_denied_total`
- `AuthorizationGuard`, `GitOpsCommitter`, `PlatformWatcherSpawner`

## Open Security Issues

Nenhuma issue ativa em `docs/security/issues/`.

## Active Specs / Plans

### Status: Approved (implementados, aguardando marcação)
- `docs/superpowers/specs/2026-05-26-resources-package-design.md` — Resources Package Design (entregue nesta sessão; mover para Implemented após merge em `main`)
- `docs/superpowers/specs/2026-05-26-interface-loader-design.md` — InterfaceLoader Design (já existe `wasp/clients/interfaces.py`; mover para Implemented)

### Status: Idea
- `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` — golden set para detectar regressões no system prompt
- `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` — alertas de orçamento de tokens
- `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` — opção A de auth (OAuth direto GitHub/Google)
- `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` — opção B de auth (Cognito como hub federado)
- 14 specs de 2026-05-26: code-quality-security-scanning, disaster-recovery, dora-metrics, eu-ai-act, helm-chart, incident-response, load-testing, opentelemetry-tracing, penetration-test, privacy-data-retention, prompt-versioning, rate-limiting, sbom, secret-rotation, supply-chain-security

### Status: Deferred
- `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` — persistir `platform_watches` em SQLite

## Next Steps

1. **Validar o branch `dev`** (já feito nesta sessão; passa em `make test` + `make e2e-with-debug`) e decidir merge em `main`
2. **Atualizar status dos specs entregues:** `2026-05-26-resources-package-design.md` e `2026-05-26-interface-loader-design.md` → `Implemented` após merge
3. **Decidir próxima feature:** muitos specs em Idea cobrem áreas distintas (auth A/B, observability, security, governance). Triar prioridade — sugestão: começar por `2026-05-20-llm-behavior-evaluation.md` (golden set evita regressões silenciosas no system prompt, como a que causou a falha intermitente do E2E nesta sessão)

## Backlog

- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite
- **Próximo CRD: `Cluster`** — seguir o padrão recém-criado: `wasp/resources/cluster/{manifest,provisioner,inventory}.py` + dois `@tool` em `wasp/provision.py`
- **Tightening do edge watcher ↔ resources** — `wasp/watcher.py` importa `PLATFORM_*` de `wasp.resources.platform` enquanto `wasp.resources.platform.{inventory,provisioner}` importam `extract_channel/extract_chat_id` de `wasp.watcher`. Bidirecional, funciona hoje; quando um terceiro CRD chegar, considere mover `extract_channel/extract_chat_id` para um módulo folha (ex: `wasp/session.py`)
- **Extensão do padrão `clients/`** (`docs/sdlc/01-exploration/clients-package-pattern.md`) — decidir se `git_client` e `gitops_committer` migram para `wasp/clients/<backend>/`
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`
- **Falha clara em configuração ausente** — validar variáveis obrigatórias no startup com mensagens explícitas
- **Authorization granular (RBAC)** — papéis (admin, operator, viewer) e mapeamento `user_id → role`

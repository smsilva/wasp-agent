# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

## Current Progress

**Ciclos 1 e 2 completos.** Pipeline Crossplane local validado end-to-end com Composition v2 + function-patch-and-transform. **Ciclo de migração Crossplane v2 completo.** **Ciclo 3 (watcher assíncrono) com spec + plan TDD aprovados — pronto para implementar.**

### Ciclo 1 (completo, mergeado em `main`)
- `main.py` — Agent + Telegram interface + SQLite storage (agno 2.6.5 API)
- `tests/conftest.py` + `tests/test_main.py` — 3 testes, 100% cobertura
- Smoke test validado: bot respondeu no Telegram, memória de sessão funcionando

### Ciclo 2 (completo + smoke test validado, mergeado em `main`)
- `tools/provision.py` — modelos Pydantic + `provision_platform_instance` tool
- `tools/__init__.py` — re-exporta `provision_platform_instance`
- `tests/test_provision.py` — 4 testes, 100% cobertura
- `main.py` — tool registrada, system prompt refinado (tom, escopo, confirmação)
- 7 testes, 100% cobertura
- Commit real confirmado em `smsilva/wasp-gitops` branch `dev`

### Pipeline Crossplane local — validado
- `manifests/crossplane/xrd/platform.yaml` — XRD em `apiextensions.crossplane.io/v2` com `scope: Cluster`
- `manifests/crossplane/compositions/platform.yaml` — Composition em modo Pipeline com `function-patch-and-transform:v0.10.5`; cria `Namespace` + `ConfigMap` derivados de `metadata.name`
- `manifests/crossplane/functions/patch-and-transform.yaml` — Function package
- `manifests/crossplane/providers/kubernetes.yaml` — `DeploymentRuntimeConfig` pinando o SA `provider-kubernetes` + `Provider` referenciando essa DRC
- `manifests/crossplane/providerconfigs/kubernetes.yaml` — `ProviderConfig default` (InjectedIdentity) + `ClusterRoleBinding cluster-admin` para o SA estável `provider-kubernetes`
- Teste end-to-end OK: aplicar `manifests/tenants/example.yaml` → Platform `example` reconcilia → Namespace `example` criado → ConfigMap `example/example` com `data.domain: wasp.silvios.me`
- Migração Crossplane v2 completa: runbook `docs/runbooks/k3d-argocd-wasp-gitops.md` atualizado (Provider+DRC, function antes da Composition, XRD v2)

### Ciclo 3 — spec + plan aprovados (branch `dev`, não implementado)
- `docs/specs/2026-05-16-platform-watcher-cycle3-design.md` — design do watcher: kube auto-detect (in-cluster → kubeconfig), polling 10s/timeout 10min, integração com `provision_platform_instance` via `run_context`, parse de `tg:{entity}:{chat_id}`, POST direto na Telegram API
- `docs/plans/2026-05-16-platform-watcher-cycle3.md` — 5 Tasks TDD (deps → helpers puros → async loop → integração → smoke), cada Task com red-green-refactor, 100% coverage e commit conventional
- `docs/specs/2026-05-16-platform-watcher-restart-resilience.md` — design deferido (SQLite `platform_watches`) para implementar **depois** do MVP

## What Worked

- `agno[anthropic,os,telegram]` como extra único cobre todas as deps runtime
- `Telegram(agent=agent, token=token)` — agent passado no construtor da interface
- Mock de `dotenv.load_dotenv` no conftest evita que `.env` real interfira nos testes
- ngrok + `setWebhook` com `secret_token` para desenvolvimento local
- `yaml.safe_dump()` previne injeção de objetos Python arbitrários em manifests GitOps
- PAT fine-grained com escopo mínimo: apenas `smsilva/wasp-gitops`, apenas Contents write
- Confirmação via LLM (system prompt) funciona bem no Telegram
- Tool retornando dict genérico com apenas `status` e `message` — LLM não vaza detalhes internos
- Composition Pipeline com `function-patch-and-transform`: patches FromCompositeFieldPath funcionam idênticos ao modo resources legacy
- Criar `Namespace` como recurso `Object` na própria pipeline antes de outros recursos namespaced — provider-kubernetes reconcilia eventualmente sem ordering explícito
- `DeploymentRuntimeConfig` com `spec.serviceAccountTemplate.metadata.name` + `Provider.spec.runtimeConfigRef` pina o SA: nome do Deployment continua tracking a revision, mas `serviceAccountName` interno é o pinado e o `ClusterRoleBinding` fica estável entre reinstalações
- Forçar reconciliação imediata de um `Object` do provider-kubernetes: `kubectl annotate object <name> reconcile=$(date +%s) --overwrite` (sem isso o `Object` reporta `Ready=True` stale por minutos após drift externo)

## What Didn't Work

- Declarar `anthropic`, `fastapi`, `uvicorn` como deps individuais — agno não os encontra; usar extras
- `Telegram(token=token)` sem `agent=` — lança `ValueError` em runtime
- `SqliteAgentStorage` / `add_history_to_messages` — não existem no agno 2.6.5; usar `SqliteDb` / `add_history_to_context`
- `DEFAULT_REGIONS = ["us-east-1"]` como default de função — lista mutável é Python gotcha; usar tupla + `None`
- `@tool(requires_confirmation=True)` com Telegram — o agno emite `RunPausedEvent` mas a interface Telegram não tem handler para ele; a tool é silenciosamente rejeitada. Usar confirmação via LLM no system prompt
- Retornar campos técnicos no dict da tool (`commit_sha`, `file_path`) — o LLM os surfacia todos ao usuário; incluir só `status` e `message`
- Nomear Composition com sufixo da implementação (`platform-configmap`) — usar o nome do tipo composto (`platform`)
- `apiextensions.crossplane.io/v1` na XRD — deprecated no Crossplane v2; usar `/v2` com `spec.scope` (imutável, exige delete/recreate da XRD para mudar)
- Composition `spec.resources` (patch-and-transform legacy) — REMOVIDO no Crossplane v2; servidor rejeita com `unknown field "spec.resources"`. Migrar para `spec.mode: Pipeline`
- Composition referenciando Namespace inexistente — provider-kubernetes não cria namespaces implicitamente; adicionar `Namespace` como recurso `Object` na pipeline
- `ClusterRoleBinding` referenciando o SA runtime-generated (`provider-kubernetes-<hash>`) — quebra silenciosamente em reinstalações do provider; sempre pinar o SA via DRC antes

## Next Steps

### Implementar Ciclo 3 — Watcher assíncrono (próxima ação)

Seguir o plano TDD em `docs/plans/2026-05-16-platform-watcher-cycle3.md` Task-por-Task:

1. **Task 1** — adicionar deps `kubernetes`, `httpx`, `pytest-asyncio`. Confirmar caminho de import de `RunContext` no agno instalado (`grep -rn "class RunContext" .venv/lib/python*/site-packages/agno`)
2. **Task 2** — `tools/watcher.py` com helpers puros: `load_kube_config_auto` (in-cluster → kubeconfig), `extract_chat_id`, `ready_message`. 5 testes
3. **Task 3** — adicionar `notify_telegram` (httpx async POST) e `watch_platform` (polling loop). 4 testes async
4. **Task 4** — integrar em `provision_platform_instance`: adicionar `run_context=None`, spawnar `asyncio.create_task(watch_platform(...))` após commit bem-sucedido. 2 testes
5. **Task 5** — smoke test end-to-end via Telegram local com ngrok + cluster k3d

### Decisões para o MVP (já registradas na spec)
- Fallback local: watcher tenta `load_incluster_config()` e cai para `load_kube_config()` (`KUBECONFIG`/`~/.kube/config`)
- Sem restart resilience no MVP — watches são in-memory only; ver spec deferida
- Polling 10s, timeout 10min
- Sem retry de POST para Telegram; sem parse_mode (texto plano)
- Platform CR é cluster-scoped (XRD `scope: Cluster`)
- Status check: `conditions[{type:"Ready", status:"True"}]` (padrão Crossplane)

### Backlog (depois do Ciclo 3)
- **Restart resilience do watcher** — persistir `platform_watches` em SQLite. Ver `docs/specs/2026-05-16-platform-watcher-restart-resilience.md`
- **Logging estruturado** — suporte opcional a JSONL via `LOG_FILE` env var. Ver `docs/specs/2026-05-16-structured-logging.md`
- **Status check manual** — tool para o usuário perguntar o estado de uma Platform (ex.: "status da plataforma wp2") sem depender do watcher
- **Operações além de criar** — update, delete, list de tenants (system prompt atual recusa explicitamente)

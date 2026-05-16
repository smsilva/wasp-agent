# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

## Current Progress

**Ciclos 1, 2 e 3 completos.** Pipeline Crossplane local validado end-to-end. **Ciclo 3 (watcher assíncrono) implementado com TDD, 22 testes, 100% cobertura — pronto para smoke test e merge.**

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

### Ciclo 3 — Watcher assíncrono (completo, branch `dev`, pendente smoke test + merge)
- `tools/watcher.py` — `load_kube_config_auto` (in-cluster → kubeconfig fallback), `extract_chat_id` (parse `tg:{entity}:{chat_id}`), `ready_message`, `notify_telegram` (httpx async POST), `watch_platform` (polling loop 10s, timeout 10min)
- `tests/test_watcher.py` — 12 testes, 100% cobertura
- `tools/provision.py` — `run_context=None` adicionado; spawna `loop.create_task(watch_platform(...))` após commit bem-sucedido se `chat_id` e `TELEGRAM_TOKEN` disponíveis
- `tests/test_provision.py` — 7 testes, 100% cobertura (22 total)
- `pyproject.toml` — deps `kubernetes>=29.0.0`, `httpx>=0.27.0`; dev `pytest-asyncio>=0.23.0`; `asyncio_mode = "auto"`
- Commits: `8e11be8`, `e92d7a9`, `a452a91`, `f632da2`
- `docs/specs/2026-05-16-platform-watcher-cycle3-design.md` — design do watcher
- `docs/plans/2026-05-16-platform-watcher-cycle3.md` — plano TDD (referência)
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

### Task 5 do Ciclo 3 — Smoke test end-to-end (próxima ação)

1. Subir agente local com ngrok + `KUBECONFIG` apontando para k3d. Ver `docs/runbooks/telegram-local-dev.md`
2. Pedir `cria plataforma wp-smoke em us-east-1` no Telegram
3. Confirmar: bot responde com status, depois ~1 min notificação proativa "Plataforma 'wp-smoke' está pronta..." com endpoint
4. Limpeza: deletar `infrastructure/tenants/wp-smoke.yaml` no `smsilva/wasp-gitops` branch `dev`
5. Após smoke test OK: merge `dev` → `main`

### Backlog (depois do Ciclo 3)
- **Restart resilience do watcher** — persistir `platform_watches` em SQLite. Ver `docs/specs/2026-05-16-platform-watcher-restart-resilience.md`
- **Logging estruturado** — suporte opcional a JSONL via `LOG_FILE` env var. Ver `docs/specs/2026-05-16-structured-logging.md`
- **Status check manual** — tool para o usuário perguntar o estado de uma Platform (ex.: "status da plataforma wp2") sem depender do watcher
- **Operações além de criar** — update, delete, list de tenants (system prompt atual recusa explicitamente)

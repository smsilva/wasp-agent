# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

## Current Progress

**Ciclos 1 e 2 completos — mergeados para `main`. Smoke test do ciclo 2 validado.**

**Ciclo 3 em preparação — pipeline Crossplane local validado end-to-end com Composition v2 + function-patch-and-transform.**

### Ciclo 1 (completo)
- `main.py` — Agent + Telegram interface + SQLite storage (agno 2.6.5 API)
- `tests/conftest.py` + `tests/test_main.py` — 3 testes, 100% cobertura
- Smoke test validado: bot respondeu no Telegram, memória de sessão funcionando

### Ciclo 2 (completo + smoke test validado)
- `tools/provision.py` — modelos Pydantic + `provision_platform_instance` tool
- `tools/__init__.py` — re-exporta `provision_platform_instance`
- `tests/test_provision.py` — 4 testes, 100% cobertura
- `main.py` — tool registrada, system prompt refinado (tom, escopo, confirmação)
- 7 testes, 100% cobertura
- Commit real confirmado em `smsilva/wasp-gitops` branch `dev`

### Pipeline Crossplane local — validado nesta sessão
- `manifests/crossplane/xrd/platform.yaml` — XRD em `apiextensions.crossplane.io/v2` com `scope: Cluster`
- `manifests/crossplane/compositions/platform.yaml` — Composition em modo Pipeline com `function-patch-and-transform:v0.10.5`; cria `Namespace` + `ConfigMap` derivados de `metadata.name`
- `manifests/crossplane/functions/patch-and-transform.yaml` — Function package
- `manifests/crossplane/providerconfigs/kubernetes.yaml` — ProviderConfig `default` com InjectedIdentity + ClusterRoleBinding cluster-admin para o SA do provider-kubernetes
- Teste end-to-end OK: aplicar `manifests/tenants/example.yaml` → Platform `example` reconcilia → Namespace `example` criado → ConfigMap `example/example` com `data.domain: wasp.silvios.me`

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

## Next Steps

### Pendências do ciclo de migração Crossplane v2
1. **`ClusterRoleBinding` com SA name fragil** — `manifests/crossplane/providerconfigs/kubernetes.yaml` usa o SA runtime-generated `provider-kubernetes-f8518c887488`, que muda em reinstalações do provider. Substituir por `DeploymentRuntimeConfig` que pina um SA com nome estável, e ajustar o binding para esse SA.
2. **Atualizar `docs/runbooks/k3d-argocd-wasp-gitops.md`** — refletir a nova estrutura de manifestos (`functions/`, `providerconfigs/`), apiVersion v2 da XRD, e o passo de instalação da `function-patch-and-transform` antes da Composition. Arquivo já aberto no IDE com modificações pendentes.

### Ciclo 3 — Watcher assíncrono
**Pré-requisito:** pipeline Crossplane local já validado nesta sessão (Namespace + ConfigMap criados via Platform).

**Implementação:**
1. `asyncio.create_task` in-process que observa status do `Platform` CRD
2. Notificação proativa no Telegram quando `Ready: True`

**Decisões já tomadas:**
- Agent rodará in-cluster (mesmo cluster do Crossplane/ArgoCD) — caso principal
- `RunContext.session_id` disponível via `run_context: RunContext` em `@tool`
- `session_id` Telegram = `tg:{entity_id}:{chat_id}` — `chat_id` é o último segmento
- Dep nova: `kubernetes` (client in-cluster), `httpx` (POST Telegram Bot API)
- Watch state persistido em SQLite: `platform_watches(name, session_id, status, created_at)`
- Notificação proativa via `POST /bot{token}/sendMessage` direto na Telegram API

**Dúvidas abertas (responder com cluster real):**
- Estrutura de `.status` do Platform CRD: validado nesta sessão — `conditions[{type:"Ready", status:"True"}]` é o padrão Crossplane. Confirmar via `kubectl get platform.wasp.silvios.me example -o jsonpath='{.status.conditions}'`
- Em qual namespace fica o recurso `Platform`? Cluster-scoped (XRD `scope: Cluster`), sem namespace
- Fallback local: watcher usa `KUBECONFIG` se disponível, ou só in-cluster no MVP?
- Restart resilience: recarregar watches pendentes do SQLite no startup, ou perder é aceitável no MVP?

### Backlog
- **Logging estruturado:** suporte opcional a JSONL via `LOG_FILE` env var. Ver `docs/specs/2026-05-16-structured-logging.md`.

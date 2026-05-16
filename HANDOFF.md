# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

## Current Progress

**Ciclos 1 e 2 completos — mergeados para `main`. Smoke test do ciclo 2 validado.**

**Ciclo 3 em preparação — scaffolding dos manifestos Crossplane locais criado.**

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

**Decisões do ciclo 2:**
- Commit direto em branch `dev` do `smsilva/wasp-gitops` (não PR)
- Path: `infrastructure/tenants/{name}.yaml`
- Pydantic models para gerar o manifesto (não Jinja2)
- PAT fine-grained no MVP (não GitHub App)
- Default domain: `wasp.silvios.me`, default region: `us-east-1`
- `yaml.safe_dump()` para serialização segura
- `DEFAULT_REGIONS` como tupla, `None` default na assinatura da função

### Scaffolding Crossplane local (esta sessão)
- `manifests/crossplane/xrd/platform.yaml` — XRD que instala o Kind `Platform` no cluster
- `manifests/crossplane/compositions/platform.yaml` — Composition `platform`: Platform → ConfigMap (nome e namespace derivam de `metadata.name`)
- `manifests/argocd/wasp-gitops-application.yaml` — Application ArgoCD (movido de `docs/runbooks/`)
- `manifests/tenants/example.yaml` — Platform instance de teste
- Runbook `docs/runbooks/k3d-argocd-wasp-gitops.md` atualizado com passos 4–6: provider-kubernetes, aplicar XRD+Composition, testar com example

## What Worked

- `agno[anthropic,os,telegram]` como extra único cobre todas as deps runtime
- `Telegram(agent=agent, token=token)` — agent passado no construtor da interface
- Mock de `dotenv.load_dotenv` no conftest evita que `.env` real interfira nos testes
- ngrok + `setWebhook` com `secret_token` para desenvolvimento local
- `yaml.safe_dump()` previne injeção de objetos Python arbitrários em manifests GitOps
- PAT fine-grained com escopo mínimo: apenas `smsilva/wasp-gitops`, apenas Contents write
- Confirmação via LLM (system prompt) funciona bem no Telegram
- Tool retornando dict genérico com apenas `status` e `message` — LLM não vaza detalhes internos
- Compositions Crossplane: usar `metadata.name` para derivar nome **e** namespace do ConfigMap criado

## What Didn't Work

- Declarar `anthropic`, `fastapi`, `uvicorn` como deps individuais — agno não os encontra; usar extras
- `Telegram(token=token)` sem `agent=` — lança `ValueError` em runtime
- `SqliteAgentStorage` / `add_history_to_messages` — não existem no agno 2.6.5; usar `SqliteDb` / `add_history_to_context`
- `DEFAULT_REGIONS = ["us-east-1"]` como default de função — lista mutável é Python gotcha; usar tupla + `None`
- `@tool(requires_confirmation=True)` com Telegram — o agno emite `RunPausedEvent` mas a interface Telegram não tem handler para ele; a tool é silenciosamente rejeitada. Usar confirmação via LLM no system prompt
- Retornar campos técnicos no dict da tool (`commit_sha`, `file_path`) — o LLM os surfacia todos ao usuário; incluir só `status` e `message`
- Nomear Composition com sufixo da implementação (`platform-configmap`) — usar o nome do tipo composto (`platform`)

## Next Steps

### Ciclo 3 — Watcher assíncrono
**Pré-requisito:** subir o cluster k3d com os manifestos locais e validar o ciclo completo.

```bash
cd ~/git/kubernetes/lab/argo/argocd && bash run
bash crossplane-install.sh
kubectl apply --filename ~/git/wasp-agent/manifests/argocd/wasp-gitops-application.yaml
kubectl apply --filename ~/git/wasp-agent/manifests/crossplane/xrd/platform.yaml
kubectl apply --filename ~/git/wasp-agent/manifests/crossplane/compositions/platform.yaml
# instalar provider-kubernetes (ver runbook passo 4)
kubectl apply --filename ~/git/wasp-agent/manifests/tenants/example.yaml
kubectl get configmap example --namespace example --output yaml
```

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
- Estrutura de `.status` do Platform CRD: Crossplane padrão = `conditions[{type:"Ready", status:"True"}]` — confirmar
- Em qual namespace fica o recurso `Platform`?
- Fallback local: watcher usa `KUBECONFIG` se disponível, ou só in-cluster no MVP?
- Restart resilience: recarregar watches pendentes do SQLite no startup, ou perder é aceitável no MVP?

### Backlog
- **Logging estruturado:** suporte opcional a JSONL via `LOG_FILE` env var. Ver `docs/specs/2026-05-16-structured-logging.md`.

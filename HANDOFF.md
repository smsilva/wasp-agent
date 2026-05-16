# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

## Current Progress

**Ciclos 1, 2 e 3 completos e em `main`.** 22 testes, 100% cobertura. Próxima ação: smoke test end-to-end do watcher.

### Ciclo 1 (mergeado em `main`)
- `main.py` — Agent + Telegram interface + SQLite storage (agno 2.6.5 API)
- `tests/conftest.py` + `tests/test_main.py` — 3 testes, 100% cobertura
- Smoke test validado: bot respondeu no Telegram, memória de sessão funcionando

### Ciclo 2 (mergeado em `main`)
- `tools/provision.py` — modelos Pydantic + `provision_platform_instance` tool
- `tools/__init__.py` — re-exporta `provision_platform_instance`
- `tests/test_provision.py` — testes, 100% cobertura
- `main.py` — tool registrada, system prompt refinado (tom, escopo, confirmação)
- Commit real confirmado em `smsilva/wasp-gitops` branch `dev`

### Pipeline Crossplane local — validado
- XRD `apiextensions.crossplane.io/v2`, `scope: Cluster`
- Composition Pipeline com `function-patch-and-transform:v0.10.5`; cria `Namespace` + `ConfigMap`
- `DeploymentRuntimeConfig` pinando SA `provider-kubernetes`; `ProviderConfig` InjectedIdentity + `ClusterRoleBinding cluster-admin`
- Teste end-to-end OK: tenant `example` reconcilia → Namespace + ConfigMap criados

### Ciclo 3 — Watcher assíncrono (mergeado em `main`)
- `tools/watcher.py` — `load_kube_config_auto` (in-cluster → kubeconfig fallback), `extract_chat_id` (parse `tg:{entity}:{chat_id}`), `ready_message`, `notify_telegram` (httpx async POST), `watch_platform` (polling 10s, timeout 10min)
- `tools/provision.py` — `run_context=None`; spawna `loop.create_task(watch_platform(...))` após commit bem-sucedido
- `pyproject.toml` — deps `kubernetes>=29.0.0`, `httpx>=0.27.0`; dev `pytest-asyncio>=0.23.0`; `asyncio_mode = "auto"`
- `tests/test_watcher.py` — 12 testes, 100% cobertura
- `tests/test_provision.py` — 7 testes, 100% cobertura
- Total: 22 testes, 100% cobertura
- Commits: `8e11be8` → `c335345`

## What Worked

- `agno[anthropic,os,telegram]` como extra único cobre todas as deps runtime
- `Telegram(agent=agent, token=token)` — agent passado no construtor da interface
- Mock de `dotenv.load_dotenv` no conftest evita que `.env` real interfira nos testes
- ngrok + `setWebhook` com `secret_token` para desenvolvimento local
- `yaml.safe_dump()` previne injeção de objetos Python arbitrários em manifests GitOps
- PAT fine-grained com escopo mínimo: apenas `smsilva/wasp-gitops`, apenas Contents write
- Confirmação via LLM (system prompt) funciona bem no Telegram
- Tool retornando dict com apenas `status` e `message` — LLM não vaza detalhes internos
- Composition Pipeline com `function-patch-and-transform`: patches FromCompositeFieldPath funcionam idênticos ao modo resources legacy
- `DeploymentRuntimeConfig` + `Provider.spec.runtimeConfigRef` pina SA: `ClusterRoleBinding` estável entre reinstalações
- `kubectl annotate object <name> reconcile=$(date +%s) --overwrite` força reconciliação imediata no provider-kubernetes
- `asyncio_mode = "auto"` no `[tool.pytest.ini_options]` evita `@pytest.mark.asyncio` em cada teste async
- `itertools.chain([v1], repeat(vN))` em mocks de `time.monotonic` — nunca exaure o iterator mesmo com chamadas extras no teardown do event loop
- Criar `FakeConfigException(Exception)` / `FakeApiException(Exception)` e patchear via `monkeypatch.setattr` para usar em `raise`/`except` com módulos mockados

## What Didn't Work

- Declarar `anthropic`, `fastapi`, `uvicorn` como deps individuais — agno não os encontra; usar extras
- `Telegram(token=token)` sem `agent=` — lança `ValueError` em runtime
- `SqliteAgentStorage` / `add_history_to_messages` — não existem no agno 2.6.5; usar `SqliteDb` / `add_history_to_context`
- `DEFAULT_REGIONS = ["us-east-1"]` como default de função — lista mutável é Python gotcha; usar tupla + `None`
- `@tool(requires_confirmation=True)` com Telegram — agno emite `RunPausedEvent` mas Telegram não tem handler; usar confirmação via LLM no system prompt
- Retornar campos técnicos no dict da tool (`commit_sha`, `file_path`) — LLM os surfacia ao usuário; incluir só `status` e `message`
- `apiextensions.crossplane.io/v1` na XRD — usar `/v2`; `scope` é imutável (exige delete/recreate)
- Composition `spec.resources` — REMOVIDO no Crossplane v2; usar `spec.mode: Pipeline`
- `ClusterRoleBinding` com SA runtime-generated — quebra em reinstalações; pinar via DRC
- `monkeypatch.setattr("tools.provision.asyncio.get_running_loop", ...)` — dotted string falha; usar `monkeypatch.setattr(asyncio, "get_running_loop", ...)` com módulo real importado no teste
- `iter([v1, v2])` ao mockar `time.monotonic` em testes async — esgota no teardown; usar `chain+repeat`
- `MagicMock` como classe de exceção em `raise`/`except` — não herda de `BaseException`; criar classe real e patchear

## Next Steps

### Task 5 — Smoke test end-to-end do watcher (próxima ação)

1. Subir agente local: ngrok + webhook (`docs/runbooks/telegram-local-dev.md`). Garantir `KUBECONFIG` apontando para cluster k3d.
2. Pedir `cria plataforma wp-smoke em us-east-1` no Telegram.
3. Confirmar:
   - Bot responde com status de provisioning
   - ~1 min depois: notificação proativa "Plataforma 'wp-smoke' está pronta..." com endpoint
4. Limpeza: deletar `infrastructure/tenants/wp-smoke.yaml` no `smsilva/wasp-gitops` branch `dev`.

### Backlog (depois do smoke test)
- **Restart resilience do watcher** — persistir `platform_watches` em SQLite. Ver `docs/specs/2026-05-16-platform-watcher-restart-resilience.md`
- **Logging estruturado** — suporte opcional a JSONL via `LOG_FILE` env var. Ver `docs/specs/2026-05-16-structured-logging.md`
- **Status check manual** — tool para perguntar o estado de uma Platform sem depender do watcher
- **Operações além de criar** — update, delete, list de tenants

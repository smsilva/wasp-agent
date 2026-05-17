# E2E testing do agente sem depender de chats externos

**Date:** 2026-05-17

## Problema

Hoje validar o agente E2E exige:
- ngrok rodando localmente
- Bot do Telegram registrado e com webhook apontando pro ngrok
- Smoke test manual: digitar mensagem no Telegram, observar logs, conferir notificação proativa
- Cluster k3d local com Crossplane + ArgoCD configurados (pré-existente, fora do escopo do teste)
- Acesso ao `smsilva/wasp-gitops` com `GH_PAT`

Isso é frágil, lento, não cabe em CI, e depende de infraestrutura humana (responder ao bot, abrir Telegram, confirmar ação). Cada smoke test demora ~5 min e bloqueia o desenvolvedor.

## Ideia

Pipeline E2E reprodutível e automatizado que:

1. **Sobe um cluster efêmero** (k3d ou vcluster — decidir).
2. **Deploya o stack inteiro**: Crossplane + providers (`provider-kubernetes`, etc.), ArgoCD, XRD/Composition do `Platform`, ApplicationSet.
3. **Deploya o agente** como pod no cluster (Deployment + Service + Secret com `GH_PAT` falso ou repo gitops mock).
4. **Dispara o fluxo via REST** — agno expõe FastAPI em `:7777`. Em vez de Telegram, fala diretamente com a interface HTTP do agente (`POST /agents/wasp-agent/runs` ou similar). Não precisa de Telegram, ngrok, nada.
5. **Verifica side effects**:
   - Commit chegou ao repo gitops (mock: gitea local ou volume? GitHub real com cleanup?)
   - Platform CR foi criada no cluster
   - ArgoCD reconciliou e Crossplane provisionou
   - Watcher detectou Ready e tentou notificar (Telegram mockado por server local que captura o POST)
6. **Verifica métricas**: `curl http://agent:7777/telemetry/prometheus`, parsea, confere counters incrementados.
7. **Tear down** completo: `k3d cluster delete` (ou `vcluster delete`).

## Decisões a brainstormar

### Cluster: k3d vs vcluster vs kind

| Critério | k3d | vcluster | kind |
|---|---|---|---|
| Tempo de subida | ~30s | ~10s (dentro de cluster host) | ~45s |
| Isolamento | container Docker | namespace + pod no host k8s | container Docker |
| CRDs próprios | sim | sim | sim |
| CI-friendly | bom | precisa de cluster host | ótimo |
| Roda em GH Actions | sim (Docker) | precisa cluster | sim (Docker) |
| Dev local rápido | bom | excelente se já tem k8s | bom |

**Provável escolha**: k3d local para dev (já é o que o usuário usa), kind no CI. vcluster faz sentido se já houver um cluster compartilhado.

### GitOps repo: mockar GitHub ou usar real?

- **Real (`smsilva/wasp-gitops` branch dedicada de teste)**: alta fidelidade, mas exige token, rate limits, cleanup pós-test, e poluição do histórico.
- **Gitea local em container**: precisa ajustar o tool `provision_platform_instance` pra apontar pra outro host. agno + PyGithub trabalham com endpoints customizáveis? Verificar.
- **Mock do PyGithub**: rápido, mas perde validação de que o YAML é parseável pelo GitHub e disparado pro webhook do ArgoCD. Não é E2E real.

Inclinação: **Gitea local** ou **GitHub branch de teste com cleanup automático**. Decidir depois de explorar.

### Telegram: como capturar notificação proativa?

`watcher.notify_telegram` chama `https://api.telegram.org/bot<token>/sendMessage`. Pra testar:

- Subir um httpx-mock-server local (ex: `pytest-httpserver` rodando como container)
- Apontar `TELEGRAM_API_BASE` (variável que ainda não existe — precisa virar env var) pro mock server
- Mock devolve 200, registra o POST recebido
- Teste E2E faz assertion: "1 mensagem recebida, contém nome da Platform, contém URL"

Refactor pequeno em `tools/watcher.py`: tornar `TELEGRAM_API_BASE` configurável via env var (default = api.telegram.org).

### Disparar conversa: REST direto vs simular Telegram webhook?

- **REST direto na FastAPI** (`POST /agents/wasp-agent/runs` ou rota equivalente): bypass do `Telegram` interface. Não testa o parser/router do Telegram, mas testa todo o resto.
- **Simular webhook do Telegram**: POST com JSON do formato Telegram Update no endpoint que o agno expõe pra Telegram webhook. Testa um caminho a mais. Mais código no teste, mais fiel à produção.

Inclinação: REST direto na v1 (mais simples), webhook simulado na v2 (se quisermos cobrir o caminho Telegram especificamente).

### Confirmação interativa do agente

O agente pede confirmação antes de provisionar ("Confirma que quer criar 'wp-foo'?"). No fluxo automatizado, precisamos:
- Multi-turn: primeira mensagem dispara confirmação, segunda mensagem ("sim") executa.
- Ou: feature flag `AUTO_CONFIRM=true` para teste E2E que pula a confirmação. Risco: divergência entre teste e produção.

Inclinação: **multi-turn**. Mantém fidelidade e exercita o storage de sessão (SqliteDb).

### Métricas: validar nomes, tipos e valores

Após o run:
```python
metrics_text = httpx.get("http://localhost:7777/telemetry/prometheus").text
parsed = parse_prometheus(metrics_text)
assert parsed["provisioning_total"].labels(outcome="started") == 1
assert parsed["agent_tool_calls_total"].labels(tool="provision_platform_instance", status="ok") == 1
assert parsed["agent_watcher_polls_total"].labels(result="ready") >= 1
```

Usar `prometheus_client.parser.text_string_to_metric_families` ou similar pra parse.

### Onde mora o teste

- `tests/e2e/test_full_provisioning_flow.py` — marcado `@pytest.mark.e2e`, skip por default em `pytest`, ativado com `pytest -m e2e`.
- Setup/teardown via fixtures que invocam `k3d cluster create/delete`. Tempo total esperado: 2–5 min.
- CI: workflow separado (`.github/workflows/e2e.yml`) que roda em PR no `dev` antes do merge pra `main`.

## Próximos passos quando retomar

1. Decidir cluster (k3d vs kind vs vcluster) — provavelmente k3d local + kind no CI.
2. Decidir gitops mock (Gitea vs GitHub branch real vs PyGithub mock).
3. Refactor `tools/watcher.py` para tornar `TELEGRAM_API_BASE` configurável via env var.
4. Spec aprovado → plano TDD → implementação.

## Referências

- `docs/architecture/platform-provisioning.md` — fluxo atual
- `docs/architecture/async-watcher.md` — comportamento do watcher
- `docs/runbooks/telegram-local-dev.md` — fluxo manual atual
- vcluster: https://www.vcluster.com/
- k3d: https://k3d.io/
- pytest-httpserver: https://pytest-httpserver.readthedocs.io/

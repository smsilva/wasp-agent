# E2E Testing Pipeline

**Date:** 2026-05-19  
**Status:** Implemented  
**Scope:** Pipeline E2E automatizado e reprodutível, sem dependência de Telegram, ngrok, ArgoCD ou Crossplane reais.

---

## Problema

Validar o agente E2E hoje exige infraestrutura manual: ngrok, Telegram, cluster k3d pré-configurado com Crossplane + ArgoCD, e ação humana. É lento, frágil, e não cabe em CI.

## Decisões de design

| Decisão | Escolha | Motivo |
|---|---|---|
| Cluster | k3d (local + CI) | Já é o tool do dev; funciona em `ubuntu-latest` sem ajustes |
| Crossplane | ❌ fora do escopo | O agente não é responsável por testar que o Crossplane funciona |
| ArgoCD | ❌ fora do escopo | Fixture aplica o CR diretamente após validar o git push |
| Git server | Gitea em container | Push real + validação do YAML; compatível com PyGithub via `base_url` |
| Fake reconciler | Thread no fixture (kubernetes client) | Controla timing sem infraestrutura extra |
| Multi-turn | Real (dois POSTs com mesmo `session_id`) | Exercita SqliteDb e o fluxo de confirmação de produção |
| Notificação | Protocolo `Notifier` + `RecordingNotifier` | Desacopla de canal; independente de Telegram/Discord/WhatsApp |
| Agente | In-process via `httpx.AsyncClient(app=app)` | Injeção direta do `RecordingNotifier`; sem subprocess ou porta TCP |
| Estrutura | `tests/e2e/`, `@pytest.mark.e2e`, `--no-cov` | Separa do threshold de 100% dos testes unitários |

## Fluxo E2E

```
fixture: k3d cluster + CRDs + Gitea container
         ↓
test:    POST /agents/wasp-agent/runs  → "Cria platform wp-test"
         ↓ agente pede confirmação
test:    POST /agents/wasp-agent/runs  → "sim"  (mesmo session_id)
         ↓ provision_platform_instance executa
         ↓ push YAML → Gitea
fixture: valida conteúdo do commit no Gitea API
fixture: aplica Platform CR no k3d
         ↓
fixture: thread fake-reconciler → kubectl patch status Ready (após 3s)
         ↓
watcher: detecta Ready → Notifier.send()
test:    assert RecordingNotifier.messages == [esperado]
test:    assert métricas /telemetry/prometheus incrementadas
```

## Componentes a implementar

### 1. `Notifier` protocol (`tools/notifier.py`)

```python
class Notifier(Protocol):
    async def send(self, chat_id: str, text: str) -> None: ...

class TelegramNotifier:
    async def send(self, chat_id: str, text: str) -> None:
        # lógica atual de notify_telegram

class RecordingNotifier:
    messages: list[dict]  # {"chat_id": ..., "text": ...}
    async def send(self, chat_id: str, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})
```

### 2. Refactor `tools/watcher.py`

- Remover `notify_telegram` (função standalone)
- `watch_platform` recebe `notifier: Notifier` como parâmetro
- `main.py` injeta `TelegramNotifier()`

### 3. Configurabilidade do git endpoint (`tools/provision.py`)

```python
base_url = os.getenv("GITHUB_BASE_URL", "https://api.github.com")
repo_name = os.getenv("GITOPS_REPO", "smsilva/wasp-gitops")
gh = Github(base_url=base_url, login_or_token=pat)
```

### 4. Fixtures E2E (`tests/e2e/conftest.py`)

- `k3d_cluster`: cria cluster efêmero, instala CRDs (XRD do Platform), destrói no teardown
- `gitea_container`: sobe Gitea via `docker run`, cria repo `wasp-gitops`, destrói no teardown
- `fake_reconciler`: thread que assiste Platform CRs e faz `kubectl patch` de status Ready após 3s
- `agent_client`: `httpx.AsyncClient` com `app=app` e `RecordingNotifier` injetado

### 5. Teste (`tests/e2e/test_full_provisioning_flow.py`)

```python
@pytest.mark.e2e
async def test_provision_and_notify(agent_client, gitea, fake_reconciler, notifier):
    # turn 1
    r1 = await agent_client.post("/agents/wasp-agent/runs", json={"message": "Cria platform wp-test", "session_id": SESSION})
    assert "confirma" in r1.json()["content"].lower()

    # turn 2
    r2 = await agent_client.post("/agents/wasp-agent/runs", json={"message": "sim", "session_id": SESSION})
    assert r2.status_code == 200

    # git push
    commit = gitea.get_latest_commit("wasp-gitops")
    yaml_content = gitea.get_file(commit, "tenants/wp-test.yaml")
    assert "wp-test" in yaml_content

    # notificação
    await asyncio.wait_for(notifier.wait_for_message(), timeout=30)
    assert any("wp-test" in m["text"] for m in notifier.messages)

    # métricas
    metrics = httpx.get("http://testserver/telemetry/prometheus").text
    assert 'agent_provisioning_total{outcome="started"}' in metrics
```

### 6. CI (`.github/workflows/e2e.yml`)

- Trigger: `pull_request` para `dev`
- Runner: `ubuntu-latest`
- Steps: instala k3d, Docker disponível, `uv run pytest -m e2e --no-cov`
- Separado do `ci.yaml` existente (que só faz build/push de imagem)

### 7. `pyproject.toml`

```toml
[tool.pytest.ini_options]
markers = ["e2e: end-to-end tests requiring k3d and Gitea"]

[tool.coverage.run]
omit = ["tests/*", "smoke_*.py", "tests/e2e/*"]
```

## Critérios de sucesso

1. `pytest` (sem flags) continua passando com 100% de cobertura e ruff clean
2. `pytest -m e2e --no-cov` executa o fluxo completo em menos de 5 min
3. O commit no Gitea contém o YAML correto para `wp-test`
4. `RecordingNotifier` captura exatamente 1 mensagem com "wp-test"
5. Métrica `agent_provisioning_total{outcome="started"}` == 1
6. `.github/workflows/e2e.yml` passa em PR para `dev`

## Ordem de implementação

1. `Notifier` protocol + `TelegramNotifier` + `RecordingNotifier` → atualizar testes unitários do watcher
2. Configurabilidade `GITHUB_BASE_URL` + `GITOPS_REPO` em `provision.py` → atualizar testes unitários
3. Fixtures `k3d_cluster` + `gitea_container` + `fake_reconciler` + `agent_client`
4. Teste E2E `test_full_provisioning_flow.py`
5. `.github/workflows/e2e.yml`
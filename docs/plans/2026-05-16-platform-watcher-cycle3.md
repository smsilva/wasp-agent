# Platform Watcher — Cycle 3 Implementation Plan

**Goal:** Implementar o watcher in-process do Ciclo 3 conforme a spec [`2026-05-16-platform-watcher-cycle3-design.md`](../specs/2026-05-16-platform-watcher-cycle3-design.md). MVP sem persistência — watches são in-memory only e perdidos no restart.

**Approach:** TDD strict (red-green-refactor). Cobertura 100% verificada com `pytest --cov`. Cada Task termina com `ruff check .` limpo e commit conventional.

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Adicionar `kubernetes` e `httpx` em `[project].dependencies`**

```toml
dependencies = [
    "agno[anthropic,os,telegram]>=2.0.0",
    "python-dotenv>=1.0.0",
    "sqlalchemy>=2.0.0",
    "PyGithub>=2.0.0",
    "pyyaml>=6.0",
    "kubernetes>=29.0.0",
    "httpx>=0.27.0",
]
```

- [ ] **Step 2: Adicionar `pytest-asyncio` em `[dependency-groups].dev`** (ou `[project.optional-dependencies].dev`, conforme a estrutura atual do `pyproject.toml`)

```toml
"pytest-asyncio>=0.23.0",
```

- [ ] **Step 3: `uv sync`**

```bash
uv sync
```

- [ ] **Step 4: Verificar imports**

```bash
python -c "import kubernetes; import httpx; import pytest_asyncio; print('ok')"
```

Esperado: `ok`.

- [ ] **Step 5: Confirmar caminho de `RunContext` no agno instalado**

```bash
grep -rn "class RunContext" .venv/lib/python*/site-packages/agno | head -5
```

Anotar o módulo (ex.: `agno.run.response` ou `agno.agent.run_context`). Será usado nos imports da Task 4.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add kubernetes, httpx, pytest-asyncio for watcher"
```

---

### Task 2: `tools/watcher.py` — kube config auto-detect + helpers puros

**Files:**
- Create: `tools/watcher.py`
- Create: `tests/test_watcher.py`
- Modify: `tests/conftest.py` (adicionar mocks de `kubernetes` e `httpx`)

- [ ] **Step 1: Atualizar `tests/conftest.py`**

Adicionar aos módulos mockados:

```python
EXTERNAL_MODULES_TO_MOCK = [
    "kubernetes",
    "kubernetes.client",
    "kubernetes.config",
]
```

E mockar no fixture (mesma técnica usada para os módulos do agno). Não mockar `httpx` no conftest — preferimos `monkeypatch.setattr` por teste para ter controle granular sobre `AsyncClient`.

Adicionar `tools.watcher` ao set de módulos a limpar entre testes.

- [ ] **Step 2: Testes falhando para helpers puros**

`tests/test_watcher.py`:

```python
import pytest


def test_extract_chat_id_from_telegram_session():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    assert extract_chat_id(FakeCtx()) == "5621932873"


def test_extract_chat_id_returns_none_for_non_telegram():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "web:abc:def"

    assert extract_chat_id(FakeCtx()) is None
    assert extract_chat_id(None) is None


def test_ready_message_includes_endpoints():
    from tools.watcher import ready_message

    platform = {
        "spec": {
            "regions": [
                {"name": "us-east-1", "endpoint": "gateway.us-east-1.wp2.wasp.silvios.me"},
                {"name": "sa-east-1", "endpoint": "gateway.sa-east-1.wp2.wasp.silvios.me"},
            ]
        }
    }
    msg = ready_message("wp2", platform)
    assert "wp2" in msg
    assert "us-east-1" in msg
    assert "https://gateway.us-east-1.wp2.wasp.silvios.me" in msg
    assert "https://gateway.sa-east-1.wp2.wasp.silvios.me" in msg


def test_load_kube_config_auto_incluster(monkeypatch):
    from unittest.mock import MagicMock
    import tools.watcher as w

    incluster = MagicMock()
    local = MagicMock()
    monkeypatch.setattr(w.config, "load_incluster_config", incluster)
    monkeypatch.setattr(w.config, "load_kube_config", local)

    w.load_kube_config_auto()

    incluster.assert_called_once()
    local.assert_not_called()


def test_load_kube_config_auto_fallback_local(monkeypatch):
    from unittest.mock import MagicMock
    import tools.watcher as w

    def raise_(*a, **kw):
        raise w.config.ConfigException("not in cluster")

    incluster = MagicMock(side_effect=raise_)
    local = MagicMock()
    monkeypatch.setattr(w.config, "load_incluster_config", incluster)
    monkeypatch.setattr(w.config, "load_kube_config", local)

    w.load_kube_config_auto()

    incluster.assert_called_once()
    local.assert_called_once()
```

```bash
pytest tests/test_watcher.py -v
```

Esperado: 5 FAIL (módulo `tools.watcher` não existe).

- [ ] **Step 3: Criar `tools/watcher.py` com os helpers (sem watch loop ainda)**

```python
from kubernetes import client, config


def load_kube_config_auto() -> "client.CustomObjectsApi":
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CustomObjectsApi()


def extract_chat_id(run_context) -> str | None:
    if run_context is None:
        return None
    session_id = getattr(run_context, "session_id", None)
    if not session_id:
        return None
    parts = session_id.split(":")
    if len(parts) >= 3 and parts[0] == "tg":
        return parts[-1]
    return None


def ready_message(name: str, platform: dict) -> str:
    spec = platform.get("spec", {})
    regions = spec.get("regions", [])
    lines = [f"Plataforma '{name}' está pronta."]
    for r in regions:
        endpoint = r.get("endpoint")
        if endpoint:
            lines.append(f"- {r['name']}: https://{endpoint}")
    return "\n".join(lines)
```

```bash
pytest tests/test_watcher.py -v
```

Esperado: 5 PASS.

- [ ] **Step 4: Coverage check**

```bash
pytest tests/test_watcher.py --cov=tools.watcher --cov-report=term-missing
```

Esperado: 100% em `tools/watcher.py`.

- [ ] **Step 5: Ruff**

```bash
ruff check .
```

- [ ] **Step 6: Commit**

```bash
git add tools/watcher.py tests/test_watcher.py tests/conftest.py
git commit -m "feat(watcher): add kube config auto-detect and message helpers"
```

---

### Task 3: `notify_telegram` + `watch_platform`

**Files:**
- Modify: `tools/watcher.py` (adicionar funções async)
- Modify: `tests/test_watcher.py` (adicionar 4 testes)

- [ ] **Step 1: Testes falhando — `notify_telegram`**

Append em `tests/test_watcher.py`:

```python
@pytest.mark.asyncio
async def test_notify_telegram_posts_message(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False
    cm = MagicMock(return_value=fake_client)
    monkeypatch.setattr(w.httpx, "AsyncClient", cm)

    await w.notify_telegram("12345", "fake-token", "hello")

    cm.assert_called_once()
    fake_client.post.assert_awaited_once_with(
        "https://api.telegram.org/botfake-token/sendMessage",
        json={"chat_id": "12345", "text": "hello"},
    )
```

- [ ] **Step 2: Testes falhando — `watch_platform`**

```python
@pytest.mark.asyncio
async def test_watch_platform_notifies_when_ready(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w

    api = MagicMock()
    api.get_cluster_custom_object.return_value = {
        "spec": {"regions": [{"name": "us-east-1", "endpoint": "gateway.us-east-1.wp2.wasp.silvios.me"}]},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    notify = AsyncMock()
    monkeypatch.setattr(w, "notify_telegram", notify)

    await w.watch_platform("wp2", "12345", "fake-token")

    notify.assert_awaited_once()
    args = notify.await_args.args
    assert args[0] == "12345"
    assert "wp2" in args[2]
    assert "https://gateway.us-east-1.wp2.wasp.silvios.me" in args[2]


@pytest.mark.asyncio
async def test_watch_platform_notifies_on_404(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = w.ApiException(status=404, reason="NotFound")
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    notify = AsyncMock()
    monkeypatch.setattr(w, "notify_telegram", notify)

    await w.watch_platform("wp2", "12345", "fake-token")

    notify.assert_awaited_once()
    assert "não encontrada" in notify.await_args.args[2]


@pytest.mark.asyncio
async def test_watch_platform_timeout(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import tools.watcher as w

    api = MagicMock()
    api.get_cluster_custom_object.return_value = {"status": {"conditions": []}}
    monkeypatch.setattr(w, "load_kube_config_auto", lambda: api)
    notify = AsyncMock()
    monkeypatch.setattr(w, "notify_telegram", notify)

    # Acelera o loop: sleep vira no-op e relógio salta direto para o deadline.
    monkeypatch.setattr(w.asyncio, "sleep", AsyncMock())
    times = iter([0, w.WATCH_TIMEOUT_SECONDS + 1])
    monkeypatch.setattr(w.time, "monotonic", lambda: next(times))

    await w.watch_platform("wp2", "12345", "fake-token")

    notify.assert_awaited_once()
    assert "10 minutos" in notify.await_args.args[2]
```

```bash
pytest tests/test_watcher.py -v
```

Esperado: 4 novos FAIL.

- [ ] **Step 3: Implementar `notify_telegram` e `watch_platform` em `tools/watcher.py`**

Adicionar imports e constantes:

```python
import asyncio
import time

import httpx
from kubernetes.client import ApiException

PLATFORM_GROUP = "wasp.silvios.me"
PLATFORM_VERSION = "v1alpha1"
PLATFORM_PLURAL = "platforms"
POLL_INTERVAL_SECONDS = 10
WATCH_TIMEOUT_SECONDS = 600
TELEGRAM_API_BASE = "https://api.telegram.org"
```

Funções:

```python
def _find_condition(platform: dict, type_: str) -> dict | None:
    for c in platform.get("status", {}).get("conditions", []):
        if c.get("type") == type_:
            return c
    return None


async def notify_telegram(chat_id: str, token: str, text: str) -> None:
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as http:
        await http.post(url, json={"chat_id": chat_id, "text": text})


async def watch_platform(name: str, chat_id: str, token: str) -> None:
    api = load_kube_config_auto()
    deadline = time.monotonic() + WATCH_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        try:
            platform = api.get_cluster_custom_object(
                group=PLATFORM_GROUP,
                version=PLATFORM_VERSION,
                plural=PLATFORM_PLURAL,
                name=name,
            )
        except ApiException as e:
            if e.status == 404:
                await notify_telegram(chat_id, token, f"Platform '{name}' não encontrada no cluster.")
                return
            raise

        condition = _find_condition(platform, "Ready")
        if condition and condition.get("status") == "True":
            await notify_telegram(chat_id, token, ready_message(name, platform))
            return

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    await notify_telegram(
        chat_id, token,
        f"Provisionamento de '{name}' ainda em andamento após 10 minutos. Verifique mais tarde.",
    )
```

```bash
pytest tests/test_watcher.py -v
```

Esperado: 9 PASS.

- [ ] **Step 4: Coverage**

```bash
pytest tests/test_watcher.py --cov=tools.watcher --cov-report=term-missing
```

Esperado: 100% em `tools/watcher.py`.

- [ ] **Step 5: Ruff**

```bash
ruff check .
```

- [ ] **Step 6: Commit**

```bash
git add tools/watcher.py tests/test_watcher.py
git commit -m "feat(watcher): poll Platform status and notify via Telegram"
```

---

### Task 4: Integrar watcher em `provision_platform_instance`

**Files:**
- Modify: `tools/provision.py` (adicionar `run_context`, spawnar watcher)
- Modify: `tests/test_provision.py` (1 teste novo + ajustar teste existente)

- [ ] **Step 1: Teste falhando — watcher é spawnado após commit**

Em `tests/test_provision.py`:

```python
def test_provision_spawns_watcher(monkeypatch):
    from unittest.mock import MagicMock
    from tools.provision import provision_platform_instance

    mock_github_cls = MagicMock()
    mock_repo = MagicMock()
    mock_commit = MagicMock()
    mock_commit.sha = "abc"
    mock_github_cls.return_value.get_repo.return_value = mock_repo
    mock_repo.create_file.return_value = {"commit": mock_commit, "content": MagicMock()}

    create_task = MagicMock()
    loop = MagicMock()
    loop.create_task = create_task

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("tools.provision.Github", mock_github_cls)
    monkeypatch.setattr("tools.provision.asyncio.get_running_loop", lambda: loop)

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    result = provision_platform_instance(
        name="wp2", domain="wasp.silvios.me", regions=["us-east-1"], run_context=FakeCtx(),
    )

    create_task.assert_called_once()
    assert result["status"] == "provisioning"


def test_provision_skips_watcher_without_chat_id(monkeypatch):
    from unittest.mock import MagicMock
    from tools.provision import provision_platform_instance

    mock_github_cls = MagicMock()
    mock_repo = MagicMock()
    mock_commit = MagicMock()
    mock_commit.sha = "abc"
    mock_github_cls.return_value.get_repo.return_value = mock_repo
    mock_repo.create_file.return_value = {"commit": mock_commit, "content": MagicMock()}

    loop = MagicMock()
    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("tools.provision.Github", mock_github_cls)
    monkeypatch.setattr("tools.provision.asyncio.get_running_loop", lambda: loop)

    class FakeCtx:
        session_id = "web:abc:def"

    result = provision_platform_instance(
        name="wp2", domain="wasp.silvios.me", regions=["us-east-1"], run_context=FakeCtx(),
    )

    loop.create_task.assert_not_called()
    assert result["status"] == "provisioning"
```

```bash
pytest tests/test_provision.py::test_provision_spawns_watcher tests/test_provision.py::test_provision_skips_watcher_without_chat_id -v
```

Esperado: 2 FAIL.

- [ ] **Step 2: Modificar `tools/provision.py`**

Imports adicionais:

```python
import asyncio
from tools.watcher import extract_chat_id, watch_platform
```

> Se a confirmação da Task 1 Step 5 indicar um caminho específico para `RunContext`, importar como tipo opcional só para anotação. Se a injeção do agno funciona sem o tipo declarado, manter `run_context=None` sem anotar.

Assinatura ajustada:

```python
@tool
def provision_platform_instance(
    name: str,
    domain: str = DEFAULT_DOMAIN,
    regions: list[str] | None = None,
    requested_by: str = "",
    run_context=None,
) -> dict:
    ...
```

Após `repo.create_file(...)` bem-sucedido e antes do `return`:

```python
chat_id = extract_chat_id(run_context)
token = os.getenv("TELEGRAM_TOKEN")
if chat_id and token:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(watch_platform(name, chat_id, token))
    except RuntimeError:
        pass
```

- [ ] **Step 3: Rodar todos os testes**

```bash
pytest -v
```

Esperado: todos PASS.

- [ ] **Step 4: Coverage total**

```bash
pytest --cov --cov-report=term-missing
```

Esperado: 100% em `main.py`, `tools/__init__.py`, `tools/provision.py`, `tools/watcher.py`.

- [ ] **Step 5: Ruff**

```bash
ruff check .
```

- [ ] **Step 6: Commit**

```bash
git add tools/provision.py tests/test_provision.py
git commit -m "feat(provision): spawn Platform watcher after successful commit"
```

---

### Task 5: Smoke test end-to-end

**Files:** nenhum — apenas validação manual.

- [ ] **Step 1: Subir o agente local**

ngrok + webhook conforme `docs/runbooks/telegram-local-dev.md`. Garantir que `KUBECONFIG` aponta para o cluster k3d.

- [ ] **Step 2: Pedir provisionamento no Telegram**

Mensagem: `cria plataforma wp-smoke em us-east-1`.

- [ ] **Step 3: Confirmar e aguardar**

Esperado:
1. Bot mostra confirmação com domínio default e endpoint derivado
2. Após confirmar, bot responde "Request accepted..."
3. Em ~1 min, bot envia mensagem proativa "Plataforma 'wp-smoke' está pronta..." com o endpoint

- [ ] **Step 4: Limpeza**

```bash
# Reverter o commit no wasp-gitops (ou aplicar prune via ArgoCD)
gh -R smsilva/wasp-gitops api repos/smsilva/wasp-gitops/contents/infrastructure/tenants/wp-smoke.yaml --method DELETE --field message="chore: cleanup smoke test" --field branch=dev --field sha=$(gh ...)
```

(Pode também simplesmente deletar o arquivo no GitHub UI.)

- [ ] **Step 5: Atualizar HANDOFF.md**

Marcar Ciclo 3 como completo no `HANDOFF.md`; mover decisões relevantes para `CLAUDE.md` se aplicável; deixar a spec de restart resilience como próximo backlog.

---

## Notes

- `RunContext` no agno 2.6.5: validar caminho exato antes de codar (Task 1 Step 5). Se o agno injeta o contexto via inspeção de assinatura, talvez nem precise importar o tipo.
- Se `pytest-asyncio` exigir `asyncio_mode = "auto"` no `pyproject.toml`, adicionar:
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  ```
  e remover `@pytest.mark.asyncio` dos testes.
- `notify_telegram` usa `httpx.AsyncClient` direto — agno **não** propaga o cliente HTTP da interface Telegram, então abrimos um novo. Não é problema de performance: a chamada acontece uma vez por watcher.

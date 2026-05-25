# Platform Provision Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refatorar `provision_platform_instance` (CC=15 → ≤10) decompondo em classes, e adicionar nova tool `list_platform_instances` que reporta status real do K8s.

**Architecture:** Quatro classes de domínio (`AuthorizationGuard`, `GitOpsCommitter`, `PlatformClusterReader`, `PlatformWatcherSpawner`) + dois orquestradores (`PlatformProvisioner`, `PlatformInventory`). Entry points `@tool` viram delegadores finos.

**Tech Stack:** Python 3.14, pytest + pytest-cov, ruff, pydantic, opentelemetry, kubernetes-python, PyGithub.

**Spec:** `docs/sdlc/02-design/2026-05-25-platform-provision-refactor.md`

---

## File Structure

```
wasp/
├── auth_guard.py          # NEW: AuthorizationGuard
├── gitops_committer.py    # NEW: GitOpsCommitter
├── platform_cluster.py    # NEW: PlatformClusterReader
├── watcher.py             # MODIFY: + _select_notifier (movido de provision.py) + PlatformWatcherSpawner
├── provision.py           # MODIFY: -inline logic +PlatformProvisioner +PlatformInventory +list_platform_instances
└── __init__.py            # MODIFY: export list_platform_instances

tests/
├── test_auth_guard.py     # NEW
├── test_gitops_committer.py  # NEW
├── test_platform_cluster.py  # NEW
├── test_watcher.py        # MODIFY: + PlatformWatcherSpawner + _select_notifier tests (movidos de test_provision.py)
├── test_provision.py      # MODIFY: ajustar patches; remover _select_notifier tests; +PlatformInventory tests
├── test_complexity.py     # MODIFY: MAX_COMPLEXITY = 10
├── conftest.py            # MODIFY: + "wasp.auth_guard", "wasp.gitops_committer", "wasp.platform_cluster" no sys.modules.pop
├── e2e/conftest.py        # MODIFY: patch target _select_notifier → wasp.watcher
└── e2e/test_list_e2e.py   # NEW (opcional, ver Task 10)

main.py                    # MODIFY: import + tools=[..., list_platform_instances] + system prompt
```

---

## Task 1: AuthorizationGuard

**Files:**
- Create: `wasp/auth_guard.py`
- Create: `tests/test_auth_guard.py`
- Modify: `tests/conftest.py` (adicionar `wasp.auth_guard` ao sys.modules.pop)

- [ ] **Step 1.1: Adicionar `wasp.auth_guard` ao conftest cleanup**

Em `tests/conftest.py`, dentro dos dois loops `for mod in (...)`, adicionar `"wasp.auth_guard"`:

```python
    for mod in (
        "main",
        "wasp",
        "wasp.logging",
        "wasp.provision",
        "wasp.watcher",
        "wasp.telemetry",
        "wasp.auth",
        "wasp.auth_cli",
        "wasp.auth_guard",
    ):
        sys.modules.pop(mod, None)
```

Aplicar ambos os blocos (linhas ~48 e ~74).

- [ ] **Step 1.2: Escrever testes**

Criar `tests/test_auth_guard.py`:

```python
from unittest.mock import MagicMock


def test_guard_returns_none_when_no_channel():
    from wasp.auth_guard import AuthorizationGuard

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel=None, chat_id=None, span=span)

    assert user_id is None
    assert err is None
    span.set_attribute.assert_not_called()


def test_guard_returns_local_operator_for_trusted_channel():
    from wasp.auth_guard import AuthorizationGuard

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(
        channel="local", chat_id="abc", span=span
    )

    assert user_id == "local-operator"
    assert err is None
    span.set_attribute.assert_any_call("auth.channel", "local")
    span.set_attribute.assert_any_call("user.id", "local-operator")


def test_guard_authorizes_known_tg_user(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard

    monkeypatch.setattr("wasp.auth.is_authorized", lambda c, i: "user-abc")
    span = MagicMock()
    user_id, err = AuthorizationGuard().check(
        channel="tg", chat_id="111", span=span
    )

    assert user_id == "user-abc"
    assert err is None
    span.set_attribute.assert_any_call("auth.channel", "tg")
    span.set_attribute.assert_any_call("user.id", "user-abc")


def test_guard_denies_unknown_tg_user(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard
    import wasp.telemetry as telemetry

    monkeypatch.setattr("wasp.auth.is_authorized", lambda c, i: None)
    auth_denied_calls = []
    monkeypatch.setattr(
        telemetry, "auth_denied", lambda **kw: auth_denied_calls.append(kw)
    )

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(
        channel="tg", chat_id="999", span=span
    )

    assert user_id is None
    assert err == {"status": "unauthorized", "message": "Acesso negado."}
    assert auth_denied_calls == [{"channel": "tg", "reason": "unknown_identity"}]
    span.set_attribute.assert_any_call("auth.channel", "tg")


def test_guard_denies_when_chat_id_missing(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard
    import wasp.telemetry as telemetry

    called = []
    monkeypatch.setattr(
        "wasp.auth.is_authorized",
        lambda c, i: called.append((c, i)) or "user-abc",
    )
    monkeypatch.setattr(telemetry, "auth_denied", lambda **kw: None)

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel="tg", chat_id=None, span=span)

    assert user_id is None
    assert err == {"status": "unauthorized", "message": "Acesso negado."}
    assert called == []
```

- [ ] **Step 1.3: Rodar — esperado FAIL (ModuleNotFoundError)**

```bash
uv run pytest tests/test_auth_guard.py -v
```

Expected: erro de import (`wasp.auth_guard` não existe).

- [ ] **Step 1.4: Implementar `wasp/auth_guard.py`**

```python
import logging

import wasp.telemetry as telemetry
from wasp import auth

log = logging.getLogger(__name__)

TRUSTED_CHANNELS = {"local"}


class AuthorizationGuard:
    def check(
        self, channel: str | None, chat_id: str | None, span
    ) -> tuple[str | None, dict | None]:
        if channel is None:
            return None, None

        span.set_attribute("auth.channel", channel)

        if channel in TRUSTED_CHANNELS:
            user_id = "local-operator"
            span.set_attribute("user.id", user_id)
            return user_id, None

        user_id = auth.is_authorized(channel, chat_id) if chat_id else None
        if user_id is None:
            log.warning("auth denied: channel=%s channel_id=%s", channel, chat_id)
            telemetry.auth_denied(channel=channel, reason="unknown_identity")
            return None, {"status": "unauthorized", "message": "Acesso negado."}

        span.set_attribute("user.id", user_id)
        return user_id, None
```

- [ ] **Step 1.5: Rodar — esperado PASS**

```bash
uv run pytest tests/test_auth_guard.py -v
```

Expected: 5 passed.

- [ ] **Step 1.6: Verificar lint**

```bash
uv run ruff check wasp/auth_guard.py tests/test_auth_guard.py
```

Expected: All checks passed!

- [ ] **Step 1.7: Commit**

```bash
git add wasp/auth_guard.py tests/test_auth_guard.py tests/conftest.py
git commit -m "feat(auth_guard): extract AuthorizationGuard class from provision

Encapsula a checagem de auth (TRUSTED_CHANNELS + auth.is_authorized +
telemetria + span attributes) numa classe reusável. Não usada ainda — será
plugada em PlatformProvisioner na Task 5."
```

---

## Task 2: GitOpsCommitter

**Files:**
- Create: `wasp/gitops_committer.py`
- Create: `tests/test_gitops_committer.py`
- Modify: `tests/conftest.py` (+ `wasp.gitops_committer`)

- [ ] **Step 2.1: Adicionar `wasp.gitops_committer` ao conftest cleanup**

Mesmo padrão da Task 1.1, em ambos os loops.

- [ ] **Step 2.2: Escrever testes**

Criar `tests/test_gitops_committer.py`:

```python
from unittest.mock import MagicMock

import pytest


def test_commit_success():
    from wasp.gitops_committer import GitOpsCommitter

    client = MagicMock()
    committer = GitOpsCommitter(client=client)

    result = committer.commit(
        file_path="infrastructure/tenants/acme.yaml",
        yaml_content="apiVersion: x\n",
        commit_message="feat(tenants): provision acme",
    )

    assert result is None
    client.create_file.assert_called_once_with(
        path="infrastructure/tenants/acme.yaml",
        message="feat(tenants): provision acme",
        content="apiVersion: x\n",
        branch="dev",
    )


def test_commit_returns_already_provisioning_on_conflict():
    from wasp.git_client import FileAlreadyExistsError
    from wasp.gitops_committer import GitOpsCommitter

    client = MagicMock()
    client.create_file.side_effect = FileAlreadyExistsError(
        "infrastructure/tenants/acme.yaml"
    )
    committer = GitOpsCommitter(client=client)

    result = committer.commit(
        file_path="infrastructure/tenants/acme.yaml",
        yaml_content="x",
        commit_message="x",
    )

    assert result == {
        "status": "already_provisioning",
        "message": "Tenant 'acme' is already being provisioned.",
    }


def test_from_env_raises_when_pat_missing(monkeypatch):
    from wasp.gitops_committer import GitOpsCommitter

    monkeypatch.delenv("GH_PAT", raising=False)

    with pytest.raises(ValueError, match="GH_PAT not set"):
        GitOpsCommitter.from_env()


def test_from_env_uses_defaults(monkeypatch):
    from wasp.gitops_committer import GitOpsCommitter

    mock_client_cls = MagicMock()
    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.delenv("GITOPS_REPO", raising=False)
    monkeypatch.delenv("GITHUB_BASE_URL", raising=False)
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    GitOpsCommitter.from_env()

    mock_client_cls.assert_called_once_with(
        pat="fake-pat",
        repo="smsilva/wasp-gitops",
        base_url="https://api.github.com",
    )


def test_from_env_uses_env_vars(monkeypatch):
    from wasp.gitops_committer import GitOpsCommitter

    mock_client_cls = MagicMock()
    monkeypatch.setenv("GH_PAT", "p")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setenv("GITHUB_BASE_URL", "http://localhost:3000/api/v3")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    GitOpsCommitter.from_env()

    mock_client_cls.assert_called_once_with(
        pat="p", repo="myorg/my-gitops", base_url="http://localhost:3000/api/v3"
    )
```

- [ ] **Step 2.3: Rodar — esperado FAIL**

```bash
uv run pytest tests/test_gitops_committer.py -v
```

- [ ] **Step 2.4: Implementar `wasp/gitops_committer.py`**

```python
import os
from pathlib import PurePosixPath

from wasp.git_client import FileAlreadyExistsError, GitClient, PyGithubClient


class GitOpsCommitter:
    def __init__(self, client: GitClient):
        self._client = client

    @classmethod
    def from_env(cls) -> "GitOpsCommitter":
        pat = os.getenv("GH_PAT")
        if not pat:
            raise ValueError("GH_PAT not set")
        return cls(
            PyGithubClient(
                pat=pat,
                repo=os.getenv("GITOPS_REPO", "smsilva/wasp-gitops"),
                base_url=os.getenv("GITHUB_BASE_URL", "https://api.github.com"),
            )
        )

    def commit(
        self, file_path: str, yaml_content: str, commit_message: str
    ) -> dict | None:
        try:
            self._client.create_file(
                path=file_path,
                message=commit_message,
                content=yaml_content,
                branch="dev",
            )
        except FileAlreadyExistsError:
            name = PurePosixPath(file_path).stem
            return {
                "status": "already_provisioning",
                "message": f"Tenant '{name}' is already being provisioned.",
            }
        return None
```

- [ ] **Step 2.5: Rodar — esperado PASS**

```bash
uv run pytest tests/test_gitops_committer.py -v
```

Expected: 5 passed.

- [ ] **Step 2.6: Lint + commit**

```bash
uv run ruff check wasp/gitops_committer.py tests/test_gitops_committer.py
git add wasp/gitops_committer.py tests/test_gitops_committer.py tests/conftest.py
git commit -m "feat(gitops): extract GitOpsCommitter class

Encapsula commit genérico ao repo GitOps (build path + commit_message
ficam com o caller). Tratamento de FileAlreadyExistsError aqui dentro.
Não usada ainda — plugada em PlatformProvisioner na Task 5."
```

---

## Task 3: PlatformClusterReader

**Files:**
- Create: `wasp/platform_cluster.py`
- Create: `tests/test_platform_cluster.py`
- Modify: `tests/conftest.py` (+ `wasp.platform_cluster`)

- [ ] **Step 3.1: Adicionar `wasp.platform_cluster` ao conftest cleanup**

Mesmo padrão.

- [ ] **Step 3.2: Escrever testes**

Criar `tests/test_platform_cluster.py`:

```python
from unittest.mock import MagicMock


def test_list_with_status_empty():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {"items": []}

    result = PlatformClusterReader(api=api).list_with_status()

    assert result == []


def test_list_with_status_ready():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "acme"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            }
        ]
    }

    result = PlatformClusterReader(api=api).list_with_status()

    assert result == [{"name": "acme", "status": "Ready"}]


def test_list_with_status_pending():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "globex"},
                "status": {"conditions": [{"type": "Ready", "status": "False"}]},
            }
        ]
    }

    result = PlatformClusterReader(api=api).list_with_status()

    assert result == [{"name": "globex", "status": "Pending"}]


def test_list_with_status_unknown_when_no_ready_condition():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {
        "items": [
            {"metadata": {"name": "fresh"}, "status": {"conditions": []}},
            {"metadata": {"name": "noinfo"}},
        ]
    }

    result = PlatformClusterReader(api=api).list_with_status()

    assert result == [
        {"name": "fresh", "status": "Unknown"},
        {"name": "noinfo", "status": "Unknown"},
    ]


def test_list_calls_api_with_correct_group_version_plural():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {"items": []}

    PlatformClusterReader(api=api).list_with_status()

    api.list_cluster_custom_object.assert_called_once_with(
        group="wasp.silvios.me",
        version="v1alpha1",
        plural="platforms",
    )


def test_from_env_uses_kube_config(monkeypatch):
    from wasp.platform_cluster import PlatformClusterReader

    mock_api = MagicMock()
    monkeypatch.setattr(
        "wasp.platform_cluster.load_kube_config_auto", lambda: mock_api
    )

    reader = PlatformClusterReader.from_env()

    assert reader._api is mock_api
```

- [ ] **Step 3.3: Rodar — esperado FAIL**

```bash
uv run pytest tests/test_platform_cluster.py -v
```

- [ ] **Step 3.4: Implementar `wasp/platform_cluster.py`**

```python
from wasp.watcher import (
    PLATFORM_GROUP,
    PLATFORM_PLURAL,
    PLATFORM_VERSION,
    load_kube_config_auto,
)


class PlatformClusterReader:
    def __init__(self, api):
        self._api = api

    @classmethod
    def from_env(cls) -> "PlatformClusterReader":
        return cls(api=load_kube_config_auto())

    def list_with_status(self) -> list[dict]:
        result = self._api.list_cluster_custom_object(
            group=PLATFORM_GROUP,
            version=PLATFORM_VERSION,
            plural=PLATFORM_PLURAL,
        )
        return [
            {
                "name": item["metadata"]["name"],
                "status": _status_from_conditions(item),
            }
            for item in result.get("items", [])
        ]


def _status_from_conditions(platform: dict) -> str:
    for c in platform.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return "Ready" if c.get("status") == "True" else "Pending"
    return "Unknown"
```

- [ ] **Step 3.5: Rodar — esperado PASS**

```bash
uv run pytest tests/test_platform_cluster.py -v
```

Expected: 6 passed.

- [ ] **Step 3.6: Lint + commit**

```bash
uv run ruff check wasp/platform_cluster.py tests/test_platform_cluster.py
git add wasp/platform_cluster.py tests/test_platform_cluster.py tests/conftest.py
git commit -m "feat(platform_cluster): add PlatformClusterReader for listing Platform CRs

Lê Platform CRs via kubernetes.client.CustomObjectsApi e mapeia a condition
Ready para 'Ready'/'Pending'/'Unknown'. Será usado por PlatformInventory
(list_platform_instances tool) na Task 6."
```

---

## Task 4: Mover `_select_notifier` para `wasp/watcher.py` + PlatformWatcherSpawner

**Files:**
- Modify: `wasp/watcher.py`
- Modify: `wasp/provision.py` (remover `_select_notifier`)
- Modify: `tests/test_watcher.py` (+ tests do `_select_notifier` movidos de test_provision; + PlatformWatcherSpawner)
- Modify: `tests/test_provision.py` (remover `_select_notifier` tests)
- Modify: `tests/e2e/conftest.py` (patch target `wasp.provision._select_notifier` → `wasp.watcher._select_notifier`)

- [ ] **Step 4.1: Mover `_select_notifier` para `wasp/watcher.py`**

Adicionar no topo de `wasp/watcher.py` (após os imports existentes):

```python
import os

from wasp.notifier import ConsoleNotifier, Notifier, TelegramNotifier


def _select_notifier(channel: str | None = None) -> Notifier | None:
    kind = os.getenv("WASP_AGENT_NOTIFIER")
    token = os.getenv("TELEGRAM_TOKEN")
    if kind is None:
        if channel == "local":
            kind = "console"
        elif channel == "tg":
            kind = "telegram"
        else:
            kind = "telegram" if token else "console"
    if kind == "console":
        return ConsoleNotifier()
    if kind == "telegram":
        return TelegramNotifier(token=token) if token else None
    return None
```

Em `wasp/provision.py`, **remover**:

```python
import os
...
def _select_notifier(channel: str | None = None) -> Notifier | None:
    ...
```

E remover o import `from wasp.notifier import ConsoleNotifier, Notifier, TelegramNotifier` se ele se tornar não usado nesse arquivo após a remoção da função (deixar pendente — limpeza final na Task 7).

- [ ] **Step 4.2: Adicionar `PlatformWatcherSpawner` em `wasp/watcher.py`**

No final do arquivo:

```python
import asyncio
import threading


class PlatformWatcherSpawner:
    def spawn(
        self,
        name: str,
        chat_id: str | None,
        channel: str | None,
        parent_span_ctx,
    ) -> bool:
        if not chat_id:
            return False
        chat_id_var.set(chat_id)
        notifier = _select_notifier(channel)
        if notifier is None:
            return False

        def _run_watcher():
            asyncio.run(watch_platform(name, chat_id, notifier, parent_span_ctx))

        threading.Thread(target=_run_watcher, daemon=True).start()
        return True
```

Nota: se `asyncio`/`threading` já estiverem importados em `watcher.py` no topo, **não** re-importar — usar o import existente. Em `watcher.py` atual já existe `import asyncio`. Adicionar `import threading` no topo (não dentro da classe).

- [ ] **Step 4.3: Mover testes de `_select_notifier` para `tests/test_watcher.py`**

Remover de `tests/test_provision.py` (linhas ~270-362) e copiar para o final de `tests/test_watcher.py`, alterando apenas o import:

```python
def test_select_notifier_console_when_env_explicit(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.notifier import ConsoleNotifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "console")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_telegram_when_env_explicit(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.notifier import TelegramNotifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "telegram")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_default_telegram_when_token(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.notifier import TelegramNotifier

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_default_console_without_token(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.notifier import ConsoleNotifier

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    notifier = _select_notifier()
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_returns_none_when_telegram_without_token(monkeypatch):
    from wasp.watcher import _select_notifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "telegram")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    assert _select_notifier() is None


def test_select_notifier_returns_none_for_unknown_kind(monkeypatch):
    from wasp.watcher import _select_notifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "discord")
    assert _select_notifier() is None


def test_select_notifier_local_channel_picks_console_even_with_telegram_token(
    monkeypatch,
):
    from wasp.watcher import _select_notifier
    from wasp.notifier import ConsoleNotifier

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier(channel="local")
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_tg_channel_picks_telegram(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.notifier import TelegramNotifier

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier(channel="tg")
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_env_overrides_channel(monkeypatch):
    from wasp.watcher import _select_notifier
    from wasp.notifier import ConsoleNotifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "console")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier(channel="tg")
    assert isinstance(notifier, ConsoleNotifier)
```

- [ ] **Step 4.4: Adicionar tests para `PlatformWatcherSpawner` em `tests/test_watcher.py`**

```python
def test_spawner_no_chat_id_returns_false(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    thread_cls = MagicMock()
    with patch("wasp.watcher.threading.Thread", thread_cls):
        result = PlatformWatcherSpawner().spawn(
            name="x", chat_id=None, channel="tg", parent_span_ctx=None
        )

    assert result is False
    thread_cls.assert_not_called()


def test_spawner_no_notifier_returns_false(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "telegram")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    thread_cls = MagicMock()
    with patch("wasp.watcher.threading.Thread", thread_cls):
        result = PlatformWatcherSpawner().spawn(
            name="x", chat_id="111", channel="tg", parent_span_ctx=None
        )

    assert result is False
    thread_cls.assert_not_called()


def test_spawner_spawns_thread(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "console")
    thread = MagicMock()
    thread_cls = MagicMock(return_value=thread)
    with patch("wasp.watcher.threading.Thread", thread_cls):
        result = PlatformWatcherSpawner().spawn(
            name="x", chat_id="111", channel="local", parent_span_ctx=None
        )

    assert result is True
    thread_cls.assert_called_once()
    thread.start.assert_called_once()


def test_spawner_target_runs_asyncio(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.watcher import PlatformWatcherSpawner

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "console")

    thread = MagicMock()
    thread_cls = MagicMock(return_value=thread)
    mock_watch = MagicMock()
    mock_async_run = MagicMock()

    with (
        patch("wasp.watcher.threading.Thread", thread_cls),
        patch("wasp.watcher.asyncio.run", mock_async_run),
        patch("wasp.watcher.watch_platform", mock_watch),
    ):
        PlatformWatcherSpawner().spawn(
            name="x", chat_id="111", channel="local", parent_span_ctx=None
        )
        target = thread_cls.call_args.kwargs["target"]
        target()

    mock_async_run.assert_called_once_with(mock_watch.return_value)
```

- [ ] **Step 4.5: Atualizar patch target em `tests/e2e/conftest.py`**

Buscar a linha:

```python
monkeypatch.setattr(wasp.provision, "_select_notifier", lambda *a, **kw: recording_notifier)
```

Trocar por:

```python
import wasp.watcher
monkeypatch.setattr(wasp.watcher, "_select_notifier", lambda *a, **kw: recording_notifier)
```

Se `wasp.watcher` já estiver importado, não duplicar o import.

- [ ] **Step 4.6: Remover dos `tests/test_provision.py`**

Apagar as 9 funções `test_select_notifier_*` (linhas ~270-362 do arquivo original).

- [ ] **Step 4.7: Rodar testes — esperado PASS**

```bash
uv run pytest tests/test_watcher.py tests/test_provision.py -v
```

Expected: todos os testes do watcher (incluindo `_select_notifier` e `PlatformWatcherSpawner`) e os de provision (sem os de `_select_notifier`) passam.

`make test` completo:

```bash
make test
```

Expected: tudo verde.

- [ ] **Step 4.8: Lint + commit**

```bash
uv run ruff check wasp/ tests/
git add wasp/watcher.py wasp/provision.py tests/test_watcher.py tests/test_provision.py tests/e2e/conftest.py
git commit -m "refactor(watcher): move _select_notifier and add PlatformWatcherSpawner

Move _select_notifier de wasp.provision para wasp.watcher (proximidade
de watch_platform; evita import circular quando PlatformProvisioner usar
o spawner). Adiciona PlatformWatcherSpawner.spawn() encapsulando seleção
de notifier + spawn da thread.

Tests de _select_notifier migram de test_provision para test_watcher.
Patch em tests/e2e/conftest.py atualizado para wasp.watcher._select_notifier
(ver CLAUDE.md §19)."
```

---

## Task 5: PlatformProvisioner + refactor `provision_platform_instance`

**Files:**
- Modify: `wasp/provision.py`
- Modify: `tests/test_provision.py` (ajustar patches existentes; manter cobertura)

- [ ] **Step 5.1: Adicionar `PlatformProvisioner` em `wasp/provision.py`**

Substituir todo o corpo de `provision_platform_instance` por um delegador, e adicionar a classe acima dele. Manter os pydantic models intactos.

Estrutura final esperada de `wasp/provision.py`:

```python
import logging

import wasp.telemetry as telemetry
import yaml
from agno.tools import tool
from opentelemetry import trace
from pydantic import BaseModel, Field
from wasp.auth_guard import AuthorizationGuard
from wasp.gitops_committer import GitOpsCommitter
from wasp.watcher import PlatformWatcherSpawner, extract_channel, extract_chat_id

log = logging.getLogger(__name__)

DEFAULT_DOMAIN = "wasp.silvios.me"
DEFAULT_REGIONS = ("us-east-1",)


class ServiceSpec(BaseModel):
    name: str


class RegionSpec(BaseModel):
    name: str
    endpoint: str


class PlatformSpec(BaseModel):
    domain: str
    regions: list[RegionSpec]
    services: list[ServiceSpec] = Field(
        default_factory=lambda: [
            ServiceSpec(name=s) for s in ["auth", "discovery", "callback", "portal"]
        ]
    )


class MetadataSpec(BaseModel):
    name: str


class PlatformManifest(BaseModel):
    apiVersion: str = "wasp.silvios.me/v1alpha1"
    kind: str = "Platform"
    metadata: MetadataSpec
    spec: PlatformSpec

    @classmethod
    def build(cls, name: str, domain: str, regions: list[str]) -> "PlatformManifest":
        return cls(
            metadata=MetadataSpec(name=name),
            spec=PlatformSpec(
                domain=domain,
                regions=[
                    RegionSpec(
                        name=r,
                        endpoint=f"gateway.{r}.{name}.{domain}",
                    )
                    for r in regions
                ],
            ),
        )


class PlatformProvisioner:
    def __init__(
        self,
        guard: AuthorizationGuard,
        committer: GitOpsCommitter,
        watcher_spawner: PlatformWatcherSpawner,
    ):
        self._guard = guard
        self._committer = committer
        self._watcher_spawner = watcher_spawner

    @classmethod
    def from_env(cls) -> "PlatformProvisioner":
        return cls(
            guard=AuthorizationGuard(),
            committer=GitOpsCommitter.from_env(),
            watcher_spawner=PlatformWatcherSpawner(),
        )

    def provision(
        self,
        name: str,
        domain: str,
        regions: list[str],
        requested_by: str,
        run_context,
    ) -> dict:
        span = trace.get_current_span()
        channel = extract_channel(run_context)
        chat_id = extract_chat_id(run_context)

        user_id, err = self._guard.check(channel, chat_id, span)
        if err is not None:
            return err

        try:
            yaml_content = yaml.safe_dump(
                PlatformManifest.build(
                    name=name, domain=domain, regions=regions
                ).model_dump(),
                default_flow_style=False,
                sort_keys=False,
            )
            safe_requested_by = requested_by.replace("\n", " ").replace("\r", " ")
            err = self._committer.commit(
                file_path=f"infrastructure/tenants/{name}.yaml",
                yaml_content=yaml_content,
                commit_message=(
                    f"feat(tenants): provision {name}\n\nRequested by: {safe_requested_by}"
                ),
            )
            if err is not None:
                log.info(
                    "Tenant %s already provisioning (manifest exists)",
                    name,
                    extra={"platform": name},
                )
                telemetry.provisioning_counter.add(1, {"outcome": "already_provisioning"})
                return err

            span.set_attribute("platform.name", name)
            telemetry.provisioning_counter.add(1, {"outcome": "started"})

            spawned = self._watcher_spawner.spawn(
                name=name,
                chat_id=chat_id,
                channel=channel,
                parent_span_ctx=span.get_span_context(),
            )
            if spawned:
                span.set_attribute("watcher.spawned", True)
                log.info("Watcher spawned for %s", name, extra={"platform": name})

            return {
                "status": "provisioning",
                "message": (
                    f"Request accepted. Tenant '{name}' provisioning has started."
                    " You will be notified when the status changes."
                ),
            }
        except Exception:
            log.exception("provision_platform_instance failed", extra={"platform": name})
            telemetry.provisioning_counter.add(1, {"outcome": "error"})
            return {
                "status": "error",
                "message": "Provisioning failed. Please try again later.",
            }


@tool
@telemetry.instrument("provision_platform_instance")
def provision_platform_instance(
    name: str,
    domain: str = DEFAULT_DOMAIN,
    regions: list[str] | None = None,
    requested_by: str = "",
    run_context=None,
) -> dict:
    """
    Provisions a new Platform by committing a Crossplane manifest to
    smsilva/wasp-gitops. ArgoCD picks it up automatically.

    Returns: status (provisioning|already_provisioning|unauthorized|error) + message.
    """
    if regions is None:
        regions = list(DEFAULT_REGIONS)
    return PlatformProvisioner.from_env().provision(
        name=name,
        domain=domain,
        regions=regions,
        requested_by=requested_by,
        run_context=run_context,
    )
```

Notar:
- `TRUSTED_CHANNELS` foi para `wasp/auth_guard.py` na Task 1; remover do `provision.py`.
- `os` import some — agora só em `auth_guard.py` e `gitops_committer.py`.
- `_select_notifier` saiu (Task 4).

- [ ] **Step 5.2: Atualizar `tests/test_provision.py`**

Os testes existentes patcheiam `wasp.provision.PyGithubClient` e `wasp.provision.threading.Thread`. Esses símbolos não existem mais em `wasp.provision`. Atualizar todos os patches:

| Patch antigo | Patch novo |
|---|---|
| `wasp.provision.PyGithubClient` | `wasp.gitops_committer.PyGithubClient` |
| `wasp.provision.threading.Thread` | `wasp.watcher.threading.Thread` |
| `wasp.provision.asyncio.run` | `wasp.watcher.asyncio.run` |
| `wasp.provision.watch_platform` | `wasp.watcher.watch_platform` |
| `wasp.provision._select_notifier` | (já removido na Task 4) |

Aplicar em todos os testes do arquivo. Exemplo, `test_provision_commits`:

```python
def test_provision_commits(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    result = provision_platform_instance(
        name="wp2",
        domain="wasp.silvios.me",
        regions=["us-east-1"],
        requested_by="alice",
    )

    mock_client_cls.assert_called_once_with(
        pat="fake-pat", repo="smsilva/wasp-gitops", base_url="https://api.github.com"
    )
    call_kwargs = mock_client.create_file.call_args.kwargs
    assert call_kwargs["path"] == "infrastructure/tenants/wp2.yaml"
    assert call_kwargs["branch"] == "dev"
    assert "feat(tenants): provision wp2" in call_kwargs["message"]
    assert "Requested by: alice" in call_kwargs["message"]
    assert result["status"] == "provisioning"
    assert "wp2" in result["message"]
```

Repetir mesmo padrão em todas as outras funções (`test_provision_spawns_watcher`, `test_provision_watcher_target_runs_asyncio`, `test_provision_skips_watcher_without_chat_id`, `test_provision_creates_span`, `test_provision_records_provisioning_started`, `test_provision_uses_custom_github_base_url`, `test_provision_uses_gitops_repo_env_var`, `test_provision_spawns_watcher_with_console_notifier`, `test_provision_returns_already_provisioning_when_file_exists`, `test_provision_returns_unauthorized_when_tg_chat_id_unknown`, `test_provision_skips_auth_for_local_channel`, `test_provision_proceeds_when_tg_authorized`, `test_provision_sets_auth_channel_span_attribute_on_deny`, `test_provision_sets_user_id_span_attribute_when_authorized`, `test_provision_missing_pat`).

- [ ] **Step 5.3: Rodar — esperado PASS**

```bash
uv run pytest tests/test_provision.py -v
```

Expected: todos os testes passam.

```bash
make test
```

Expected: full suite verde, coverage 100%.

- [ ] **Step 5.4: Lint + commit**

```bash
uv run ruff check wasp/ tests/
git add wasp/provision.py tests/test_provision.py
git commit -m "refactor(provision): extract PlatformProvisioner from provision_platform_instance

provision_platform_instance vira delegator fino sobre
PlatformProvisioner.from_env().provision(). Comportamento idêntico,
assinatura idêntica. Reduz CC para <=10 no entry point e separa as quatro
responsabilidades (auth / build / commit / watcher spawn) em métodos
discretos do orquestrador."
```

---

## Task 6: PlatformInventory + tool `list_platform_instances`

**Files:**
- Modify: `wasp/provision.py` (+ PlatformInventory + list_platform_instances)
- Modify: `wasp/__init__.py` (export list_platform_instances)
- Modify: `tests/test_provision.py` (+ tests para PlatformInventory)

- [ ] **Step 6.1: Escrever testes**

Adicionar ao final de `tests/test_provision.py`:

```python
def test_list_returns_unauthorized_when_unknown_tg_chat_id(monkeypatch):
    from wasp.provision import list_platform_instances

    monkeypatch.setattr("wasp.auth.is_authorized", lambda c, i: None)

    class FakeCtx:
        session_id = "tg:wasp-agent:999"

    result = list_platform_instances(run_context=FakeCtx())

    assert result == {"status": "unauthorized", "message": "Acesso negado."}


def test_list_returns_tenants_with_status(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import list_platform_instances

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "acme"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            },
            {
                "metadata": {"name": "globex"},
                "status": {"conditions": [{"type": "Ready", "status": "False"}]},
            },
            {"metadata": {"name": "fresh"}, "status": {}},
        ]
    }
    monkeypatch.setattr(
        "wasp.platform_cluster.load_kube_config_auto", lambda: mock_api
    )

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = list_platform_instances(run_context=FakeCtx())

    assert result == {
        "status": "ok",
        "tenants": [
            {"name": "acme", "status": "Ready"},
            {"name": "globex", "status": "Pending"},
            {"name": "fresh", "status": "Unknown"},
        ],
    }


def test_list_returns_empty_list(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import list_platform_instances

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.return_value = {"items": []}
    monkeypatch.setattr(
        "wasp.platform_cluster.load_kube_config_auto", lambda: mock_api
    )

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = list_platform_instances(run_context=FakeCtx())

    assert result == {"status": "ok", "tenants": []}


def test_list_returns_error_on_exception(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import list_platform_instances

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.side_effect = RuntimeError("boom")
    monkeypatch.setattr(
        "wasp.platform_cluster.load_kube_config_auto", lambda: mock_api
    )

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = list_platform_instances(run_context=FakeCtx())

    assert result["status"] == "error"
    assert result["message"] == "List failed. Please try again later."


def test_list_creates_span(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.return_value = {"items": []}
    monkeypatch.setattr(
        "wasp.platform_cluster.load_kube_config_auto", lambda: mock_api
    )

    from wasp.provision import list_platform_instances

    list_platform_instances()

    spans = exporter.get_finished_spans()
    assert any(s.name == "list_platform_instances" for s in spans)
```

- [ ] **Step 6.2: Rodar — esperado FAIL (ImportError)**

```bash
uv run pytest tests/test_provision.py::test_list_returns_tenants_with_status -v
```

Expected: `cannot import name 'list_platform_instances'`.

- [ ] **Step 6.3: Adicionar `PlatformInventory` e `list_platform_instances` em `wasp/provision.py`**

Adicionar após `PlatformProvisioner`:

```python
from wasp.platform_cluster import PlatformClusterReader


class PlatformInventory:
    def __init__(
        self,
        guard: AuthorizationGuard,
        reader: PlatformClusterReader,
    ):
        self._guard = guard
        self._reader = reader

    @classmethod
    def from_env(cls) -> "PlatformInventory":
        return cls(
            guard=AuthorizationGuard(),
            reader=PlatformClusterReader.from_env(),
        )

    def list(self, run_context) -> dict:
        span = trace.get_current_span()
        channel = extract_channel(run_context)
        chat_id = extract_chat_id(run_context)

        user_id, err = self._guard.check(channel, chat_id, span)
        if err is not None:
            return err

        try:
            tenants = self._reader.list_with_status()
            return {"status": "ok", "tenants": tenants}
        except Exception:
            log.exception("list_platform_instances failed")
            return {"status": "error", "message": "List failed. Please try again later."}


@tool
@telemetry.instrument("list_platform_instances")
def list_platform_instances(run_context=None) -> dict:
    """
    Lists all provisioned platform instances and their cluster status.
    Returns: {"status": "ok", "tenants": [{"name": str, "status": "Ready"|"Pending"|"Unknown"}, ...]}.
    Read-only — safe to call without confirmation.
    """
    return PlatformInventory.from_env().list(run_context=run_context)
```

Mover o `from wasp.platform_cluster import PlatformClusterReader` para o bloco de imports no topo do arquivo.

- [ ] **Step 6.4: Exportar de `wasp/__init__.py`**

Atualizar `wasp/__init__.py`:

```python
from wasp.provision import list_platform_instances, provision_platform_instance

__all__ = ["list_platform_instances", "provision_platform_instance"]
```

- [ ] **Step 6.5: Rodar — esperado PASS**

```bash
uv run pytest tests/test_provision.py -v
```

Expected: todos os testes passam (incluindo os novos do list).

```bash
make test
```

Expected: full suite verde.

- [ ] **Step 6.6: Lint + commit**

```bash
uv run ruff check wasp/ tests/
git add wasp/provision.py wasp/__init__.py tests/test_provision.py
git commit -m "feat(provision): add list_platform_instances tool

PlatformInventory orquestra AuthorizationGuard + PlatformClusterReader
para listar Platform CRs com status (Ready/Pending/Unknown). Mesma auth
de provision_platform_instance — qualquer user autorizado pode listar."
```

---

## Task 7: Registrar `list_platform_instances` no agente

**Files:**
- Modify: `main.py`

- [ ] **Step 7.1: Escrever teste**

Adicionar ao final de `tests/test_main.py`:

```python
def test_agent_tools_include_list_platform_instances(monkeypatch):
    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("WASP_AGENT_ENABLE_TELEGRAM", "false")
    import main

    tool_names = {getattr(t, "__name__", None) for t in main.agent.tools}
    assert "list_platform_instances" in tool_names
    assert "provision_platform_instance" in tool_names
```

(Ajustar conforme estrutura real de `tests/test_main.py` — se o teste de tools existente usar outra estratégia, alinhar.)

- [ ] **Step 7.2: Atualizar `main.py`**

```python
from wasp import auth, list_platform_instances, provision_platform_instance  # noqa: E402
```

e

```python
agent = Agent(
    ...
    tools=[provision_platform_instance, list_platform_instances],
    ...
)
```

Adicionar ao system prompt (na string que descreve as regras das tools, próximo da linha que fala "Never call provision_platform_instance without explicit user confirmation"):

```
"list_platform_instances is read-only — safe to call without confirmation."
```

- [ ] **Step 7.3: Rodar + commit**

```bash
uv run pytest tests/test_main.py -v
make test
uv run ruff check main.py
git add main.py tests/test_main.py
git commit -m "feat(main): register list_platform_instances tool in agent

System prompt instrui o LLM que a tool é read-only — pode ser chamada
sem confirmação prévia do usuário (diferente de provision)."
```

---

## Task 8: Reduzir `MAX_COMPLEXITY` para 10

**Files:**
- Modify: `tests/test_complexity.py`

- [ ] **Step 8.1: Verificar CC máxima atual do código**

```bash
uv run radon cc wasp/ main.py -n B -s
```

Expected: nenhuma função/método ≥ 11. Se algum estiver acima, refatorar antes de mudar o limite.

- [ ] **Step 8.2: Atualizar o limite**

Em `tests/test_complexity.py`:

```python
MAX_COMPLEXITY = 10
```

- [ ] **Step 8.3: Rodar**

```bash
uv run pytest tests/test_complexity.py -v
```

Expected: PASS para todos os arquivos.

- [ ] **Step 8.4: Commit**

```bash
git add tests/test_complexity.py
git commit -m "chore(complexity): lower MAX_COMPLEXITY to 10

provision_platform_instance (CC=15) foi decomposto em
PlatformProvisioner.provision() + métodos auxiliares, todos abaixo de 10."
```

---

## Task 9: Sanity full-suite + E2E

- [ ] **Step 9.1: Full unit suite**

```bash
make test
```

Expected: tudo verde, coverage 100%.

- [ ] **Step 9.2: E2E suite (provision)**

```bash
make e2e-with-debug
```

Expected: cenário de provision passa fim-a-fim (Telegram → commit Gitea → notificação via RecordingNotifier). CLAUDE.md §16: e2e é obrigatório antes de marcar feature como pronta.

- [ ] **Step 9.3: Se algo falhar**

Diagnosticar com `tests/e2e/conftest.py` (debug ativo) e revisar:
- Patch do `wasp.watcher._select_notifier` (Task 4.5) — sem isso, RecordingNotifier não recebe.
- Patch do `wasp.auth.is_authorized` continua igual (CLAUDE.md §19).

---

## Task 10: E2E test para `list_platform_instances`

**Files:**
- Create: `tests/e2e/test_list_e2e.py`

(Opcional — pode ser deferido para depois do merge se cluster real for caro de subir. Mínimo viável: o teste unitário em Task 6 cobre a lógica.)

- [ ] **Step 10.1: Escrever teste E2E**

```python
import pytest


@pytest.mark.e2e
def test_list_platform_instances_returns_provisioned_tenants(agent_client):
    # Provisiona dois tenants via Telegram
    agent_client.send("/start <invite-token>")  # ou usar fixture já autorizada
    agent_client.send("provisione o tenant alpha")
    agent_client.send("provisione o tenant beta")

    # Lista
    response = agent_client.send("liste todos os tenants")

    assert "alpha" in response
    assert "beta" in response
```

(Ajustar conforme estrutura real de `tests/e2e/conftest.py` — verificar como `agent_client` fixture funciona e se há helpers para extrair texto da resposta do agent.)

- [ ] **Step 10.2: Rodar**

```bash
make e2e-with-debug
```

- [ ] **Step 10.3: Commit**

```bash
git add tests/e2e/test_list_e2e.py
git commit -m "test(e2e): add list_platform_instances end-to-end test"
```

---

## Task 11: Atualizar HANDOFF.md + arquivar spec

**Files:**
- Modify: `HANDOFF.md`
- Modify: header do spec (`Status: Implemented`)

- [ ] **Step 11.1: Atualizar status do spec**

Em `docs/sdlc/02-design/2026-05-25-platform-provision-refactor.md`, mudar header:

```
**Status:** Implemented
```

(Conforme CLAUDE.md §7 tabela: `Implemented` = "Merged to `main` — archive the file". Mover para `docs/sdlc/02-design/archived/` quando o merge para main acontecer — fora do escopo deste plano.)

- [ ] **Step 11.2: Atualizar HANDOFF.md**

Remover do backlog:

```
- **Reduzir `MAX_COMPLEXITY` para 10** — refatorar `provision_platform_instance` (`wasp/provision.py`, CC=15) e atualizar limite em `tests/test_complexity.py`.
```

Atualizar item "Operações além de criar — update, delete, list de tenants" para refletir que `list` foi entregue:

```
- **Operações além de criar** — update, delete de tenants (list entregue 2026-05-25).
```

Adicionar entrada na seção "What Worked" (opcional):

```
- **Refatoração de provision em classes:** AuthorizationGuard / GitOpsCommitter / PlatformClusterReader / PlatformWatcherSpawner + PlatformProvisioner / PlatformInventory. CC <=10 em todos os métodos. Permite adicionar list_platform_instances com baixo custo.
```

- [ ] **Step 11.3: Commit**

```bash
git add docs/sdlc/02-design/2026-05-25-platform-provision-refactor.md HANDOFF.md
git commit -m "docs(handoff): mark provision refactor implemented + clean backlog"
```

---

## Self-review checklist (executar ao final, antes de PR)

- [ ] Todo método/função em `wasp/` tem CC ≤ 10 (`uv run radon cc wasp/ -n B`)
- [ ] `make test` verde, coverage 100%
- [ ] `make e2e-with-debug` verde
- [ ] `uv run ruff check .` verde
- [ ] `provision_platform_instance` mantém assinatura idêntica e retornos idênticos para os 4 status (provisioning / already_provisioning / unauthorized / error)
- [ ] `list_platform_instances` retorna `{"status": "ok", "tenants": [...]}` com 3 status possíveis (Ready/Pending/Unknown) ou erro estruturado
- [ ] System prompt em `main.py` inclui regra "list_platform_instances is read-only"
- [ ] Tests/e2e/conftest.py atualiza patch target `wasp.watcher._select_notifier` (não mais `wasp.provision._select_notifier`)
- [ ] `MAX_COMPLEXITY = 10` em `tests/test_complexity.py`

---

## Quando fizer sentido considerar genericidade (deferido — não fazer agora)

Se um segundo recurso (User, Database, etc.) entrar no escopo:
- Generalizar `PlatformClusterReader` para `ClusterReader(group, version, plural)`.
- Possivelmente extrair um `ResourceProvisioner` abstrato com hook `build_manifest()`.

Por enquanto: YAGNI. A estrutura atual já isola o suficiente.

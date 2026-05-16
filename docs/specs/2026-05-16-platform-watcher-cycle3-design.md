# Platform Watcher — Cycle 3 Design

**Date:** 2026-05-16
**Scope:** MVP do watcher assíncrono — notificação proativa no Telegram quando a Platform alcança `Ready: True`. Restart resilience fica para depois (ver [`2026-05-16-platform-watcher-restart-resilience.md`](./2026-05-16-platform-watcher-restart-resilience.md)).

---

## Objective

Após `provision_platform_instance` comitar o manifesto no GitOps, o agente registra um watcher in-process que observa o status do CR `Platform` no cluster. Quando a condição `Ready: True` aparece, envia uma mensagem proativa ao usuário no Telegram com os endpoints da plataforma. Falhas e timeouts também são notificados.

---

## Architecture

```
wasp-agent/
├── main.py                        # passa TELEGRAM_TOKEN ao watcher via env (já presente)
├── tools/
│   ├── __init__.py
│   ├── provision.py               # recebe RunContext, spawna watcher após commit
│   └── watcher.py                 # NOVO — auto-detect kube config, watch loop, notify
└── tests/
    ├── conftest.py                # adiciona mock de kubernetes + httpx
    ├── test_provision.py          # 1 teste novo (watcher é spawnado após commit)
    └── test_watcher.py            # NOVO — testes do watcher
```

---

## Kubernetes client — auto-detect

Função `load_kube_config_auto()` em `tools/watcher.py`:

```python
from kubernetes import client, config

def load_kube_config_auto() -> client.CustomObjectsApi:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CustomObjectsApi()
```

Ordem: in-cluster primeiro (ambiente de produção), depois `KUBECONFIG`/`~/.kube/config` (dev local). Se ambos falharem, propaga `ConfigException` — o watcher loga e desiste sem afetar a sessão Telegram.

---

## Watch loop

```python
PLATFORM_GROUP = "wasp.silvios.me"
PLATFORM_VERSION = "v1alpha1"
PLATFORM_PLURAL = "platforms"
POLL_INTERVAL_SECONDS = 10
WATCH_TIMEOUT_SECONDS = 600  # 10 min

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
            await notify_telegram(chat_id, token, _ready_message(name, platform))
            return
        if condition and condition.get("status") == "False" and condition.get("reason") in {"ReconcileError"}:
            await notify_telegram(chat_id, token, f"Provisionamento de '{name}' falhou: {condition.get('message','')}")
            return

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    await notify_telegram(chat_id, token, f"Provisionamento de '{name}' ainda em andamento após 10 minutos. Verifique mais tarde.")
```

- **Por que polling:** simples, suficiente. A reconciliação Crossplane leva ~1 min; polling de 10 s é barato.
- **Timeout de 10 min:** depois disso, a tarefa termina. Usuário pode pedir status manualmente (feature futura).
- **404:** trata como "Platform não existe" — pode ter sido deletada manualmente ou o GitOps não sincronizou ainda. No MVP, desiste após o primeiro 404 (não retry).

---

## Telegram notification

```python
import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"

async def notify_telegram(chat_id: str, token: str, text: str) -> None:
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as http:
        await http.post(url, json={"chat_id": chat_id, "text": text})
```

- Sem retry: se a Telegram API falhar, o usuário perde essa notificação. Aceitável no MVP.
- Sem parse mode: texto plano, sem markdown — evita escaping bugs.

---

## Integration with `provision_platform_instance`

A tool ganha um parâmetro `run_context` injetado pelo agno:

```python
from agno.run.response import RunContext  # caminho a confirmar antes da implementação

@tool
def provision_platform_instance(
    name: str,
    domain: str = DEFAULT_DOMAIN,
    regions: list[str] | None = None,
    requested_by: str = "",
    run_context: RunContext | None = None,
) -> dict:
    ...
    # após repo.create_file(...) bem-sucedido:
    chat_id = _extract_chat_id(run_context)
    token = os.getenv("TELEGRAM_TOKEN")
    if chat_id and token:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(watch_platform(name, chat_id, token))
        except RuntimeError:
            # fora de um event loop (ex: testes unit) — silencia
            pass
    ...
```

### Parsing do `session_id`

`session_id` no Telegram tem formato `tg:{entity_id}:{chat_id}` (decisão do HANDOFF). `chat_id` é o último segmento:

```python
def _extract_chat_id(run_context: RunContext | None) -> str | None:
    if not run_context or not getattr(run_context, "session_id", None):
        return None
    parts = run_context.session_id.split(":")
    if len(parts) >= 3 and parts[0] == "tg":
        return parts[-1]
    return None
```

Se a sessão não vem do Telegram (ex.: AgentOS web UI no futuro), `_extract_chat_id` retorna `None` e o watcher não é spawnado.

---

## Mensagem "Ready"

```python
def _ready_message(name: str, platform: dict) -> str:
    spec = platform.get("spec", {})
    regions = spec.get("regions", [])
    lines = [f"Plataforma '{name}' está pronta."]
    for r in regions:
        endpoint = r.get("endpoint")
        if endpoint:
            lines.append(f"- {r['name']}: https://{endpoint}")
    return "\n".join(lines)
```

Mantém o tom austero do bot (sem emojis/exclamações). Mostra cada região com seu endpoint.

---

## Data flow

```
1. Usuário: "cria plataforma wp2 em us-east-1"
2. Agente extrai parâmetros + confirma com usuário
3. Confirmação → provision_platform_instance executa:
   a. commit no smsilva/wasp-gitops
   b. extrai chat_id do run_context.session_id
   c. spawna asyncio.create_task(watch_platform(name, chat_id, token))
   d. retorna {"status":"provisioning","message":"Request accepted..."}
4. Agente responde imediatamente ao usuário com a mensagem da tool
5. Watcher (background) faz polling do CR Platform a cada 10s
6. Quando Ready: True → POST direto na Telegram API:
   "Plataforma 'wp2' está pronta.
    - us-east-1: https://gateway.us-east-1.wp2.wasp.silvios.me"
```

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Já existe — agora também usado pelo watcher para POST direto |
| `KUBECONFIG` | Opcional — usado pelo fallback local. Default: `~/.kube/config` |

Nada novo.

---

## Dependencies

Adicionar a `pyproject.toml`:

```toml
"kubernetes>=29.0.0",
"httpx>=0.27.0",
```

`httpx` é provavelmente transitivo (agno → fastapi), mas declaramos explicitamente como dep direta — o agno já é dep direta também.

---

## Testing

Coverage threshold: 100%.

| Test | What it verifies |
|------|------------------|
| `test_load_kube_config_auto_incluster` | Tenta in-cluster primeiro; quando funciona, não chama load_kube_config |
| `test_load_kube_config_auto_fallback_local` | in-cluster falha → carrega kubeconfig local |
| `test_extract_chat_id_from_telegram_session` | `tg:5621932873:5621932873` → `"5621932873"` |
| `test_extract_chat_id_returns_none_for_non_telegram` | `web:abc:def` ou `None` → `None` |
| `test_ready_message_format` | Inclui nome e endpoints de cada região |
| `test_watch_platform_notifies_when_ready` | Mock `get_cluster_custom_object` retornando Ready=True → POST chamado uma vez |
| `test_watch_platform_notifies_on_404` | 404 → mensagem "não encontrada" |
| `test_watch_platform_timeout` | sleep mockado, deadline expira → mensagem de timeout |
| `test_notify_telegram_posts_message` | Mock httpx.AsyncClient — POST com chat_id e text corretos |
| `test_provision_spawns_watcher` | Após commit bem-sucedido, asyncio.create_task é chamado uma vez |
| `test_provision_skips_watcher_without_chat_id` | run_context com session_id `web:xxx` → não spawna |

Os testes do watcher usam `pytest.mark.asyncio` (via `pytest-asyncio`) ou wrappers `asyncio.run()` — a critério da implementação.

---

## Out of Scope

- Restart resilience (persistir watches em SQLite) — ver spec separada
- Retry de POST para Telegram em caso de erro de rede
- Backoff exponencial no polling
- Cancelamento manual de watch ("para de esperar wp2")
- Notificação de progresso intermediário (ex.: "Synced mas ainda não Ready")
- Telegram Bot API `parse_mode` (formatação rica) — texto plano basta
- Status check manual via tool ("status da plataforma wp2") — feature do próximo ciclo

---

## Open questions to validate during implementation

- Caminho exato do import `RunContext` no agno 2.6.5 — confirmar com `grep -r "class RunContext" .venv/lib/`
- agno injeta `run_context` automaticamente em tools quando o parâmetro tem o tipo anotado, ou exige decorator/registration extra? Validar via doc do agno + experimento local
- Estrutura exata de `.status.conditions` quando reconciliação **falha** (não só sucesso) — testar deletando a Composition e aplicando uma Platform

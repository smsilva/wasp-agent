# Fluxo: conversa → commit GitOps → watch Crossplane → notificação

Plano detalhado da funcionalidade onde o agente recebe uma mensagem em
linguagem natural (ex: *"preciso criar uma instância da plataforma em
LATAM"*), extrai parâmetros estruturados, comita um manifesto Crossplane
no repo GitOps, e monitora o recurso até `Ready: True`, retornando ao
usuário a URL de acesso quando estiver pronto.

Continuação do plano em `agno-multi-channel-agent.md`.

---

## Anatomia do fluxo (3 fases)

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. EXTRAÇÃO        2. AÇÃO              3. OBSERVAÇÃO             │
│  Texto → JSON      JSON → commit         Watch K8s → reply        │
│  (estruturado)     (GitHub API)          (assíncrono, minutos)    │
│  síncrono          síncrono              ASSÍNCRONO               │
└──────────────────────────────────────────────────────────────────┘
```

Ponto crítico: fases 1 e 2 são **síncronas** (segundos), fase 3 é
**assíncrona** (5–30min de provisionamento AWS via Crossplane). Isso
muda completamente o desenho — não dá pra segurar a conversa do
Telegram bloqueando.

---

## Fase 1 — Extração estruturada

Dois mecanismos do Agno:

### Pydantic `output_schema` no Agent

Quando a extração **é** a saída final.

```python
from pydantic import BaseModel, Field
from typing import Literal

class PlatformInstanceRequest(BaseModel):
    region: Literal["LATAM", "NA", "EU", "APAC"] = Field(
        description="Geographic region where to deploy"
    )
    tenant_name: str = Field(description="Tenant identifier, kebab-case")
    tier: Literal["dev", "staging", "prod"] = Field(default="dev")
    requested_by: str = Field(description="User who requested it")
```

### Tool com parâmetros tipados (recomendado para este caso)

A extração vira passo intermediário — o agente continua agindo depois.
Aqui o modelo preenche os argumentos da tool diretamente, sem código
de parsing à parte.

**Princípio:** o LLM extrai os **parâmetros**; o **template** renderiza
o YAML. Nunca peça pro LLM gerar manifesto Crossplane completo —
99% das vezes vai funcionar, mas o 1% é desastre em produção.

---

## Fase 2 — Commit no GitHub

### Opção A — GitHub MCP Server oficial

`github/github-mcp-server` (Go, oficial, mantido pela GitHub +
Anthropic) expõe ~100 ferramentas, incluindo `push_files` (commit
multi-arquivo numa branch).

```python
from agno.tools.mcp import MCPTools

async with MCPTools(
    command="docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server",
    env={"GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GH_PAT")},
) as github_mcp:
    agent = Agent(
        model=Claude(id="claude-sonnet-4-5"),
        tools=[github_mcp],
        ...
    )
```

**Prós:** zero código para manter, ~100 operações, ganha melhorias
de graça.
**Contras:** o agente "vê" todas as 100 tools (custo de tokens no
system prompt, maior superfície pra alucinar a tool errada). Overkill
quando você quer commitar UM tipo de arquivo num caminho específico.

### Opção B — Tool customizada (PyGithub / API REST) — **RECOMENDADO PARA COMEÇAR**

Função Python que faz exatamente uma coisa: renderiza template e
comita.

```python
from github import Github, Auth
from agno.tools import tool
from typing import Literal

@tool
def provision_platform_instance(
    tenant_name: str,
    region: Literal["LATAM", "NA", "EU", "APAC"],
    tier: Literal["dev", "staging", "prod"] = "dev",
    requested_by: str = "",
) -> dict:
    """
    Provisions a new platform instance by committing a Crossplane
    manifest to the GitOps repo. ArgoCD picks it up automatically.

    Returns: commit_sha, file_path, resource_name, resource_kind.
    """
    manifest = render_crossplane_manifest(
        tenant=tenant_name, region=region, tier=tier
    )
    file_path = f"tenants/{region.lower()}/{tenant_name}.yaml"

    gh = Github(auth=Auth.Token(os.getenv("GH_PAT")))
    repo = gh.get_repo("smsilva/aws-saas-platform")

    commit = repo.create_file(
        path=file_path,
        message=(
            f"feat(tenants): provision {tenant_name} in {region}\n\n"
            f"Requested by: {requested_by}"
        ),
        content=manifest,
        branch="main",
    )

    return {
        "commit_sha": commit["commit"].sha,
        "file_path": file_path,
        "resource_name": f"{tenant_name}-{region.lower()}",
        "resource_kind": "PlatformInstance",
        "namespace": "tenants",
    }
```

**Prós:**
- Intenção explícita, schema mínimo, fácil auditar e testar.
- Validação de input antes de tocar no GitHub.
- Human-in-the-loop fácil via `requires_confirmation=True`.
- Template fora do prompt do LLM (Jinja2), muito mais seguro.
- Controle exato dos privilégios do PAT.

**Contras:** código próprio para manter (mas é pouco).

### Opção C — Híbrido

Tool customizada de alto nível **+** MCP GitHub disponível para casos
não-cobertos ("crie PR de rollback", "veja último commit do repo X").
Melhor para fase madura.

### Recomendação

**Começar com B.** É um workflow de domínio (template específico,
naming convention, path por região), não operação genérica de Git.

---

## Human-in-the-loop antes do commit

Crítico para ações destrutivas/custosas. Agno tem mecanismo nativo:

```python
@tool(requires_confirmation=True)
def provision_platform_instance(...):
    ...
```

Fluxo no Telegram fica:

```
User:  Olá, eu preciso criar uma instância da plataforma em LATAM.
Bot:   Entendi. Vou criar uma instância com estes parâmetros:
       • Tenant: latam-prod-01
       • Region: LATAM
       • Tier: dev
       • File: tenants/latam/latam-prod-01.yaml
       Confirma? [Sim / Não]
User:  Sim
Bot:   ✅ Commit feito: a1b2c3d. ArgoCD vai sincronizar em ~1min.
       Vou monitorar o provisionamento e te aviso quando estiver pronto.
```

---

## Fase 3 — Monitoramento assíncrono (a parte mais delicada)

Crossplane pode levar 5–30min para `Ready: True` (provisionamento de
VPC, EKS, RDS via providers AWS).

### Padrão 1 — Polling dentro do tool call ❌ NÃO RECOMENDADO

Tool fica em loop chamando `kubectl get` até `Ready`. Bloqueia
conversa, estoura timeouts, ocupa worker, perde estado se agente cair.

### Padrão 2 — Background task + mensagem proativa ✅ RECOMENDADO

A tool de provisionamento:

1. Faz o commit.
2. Dispara **background task** (Celery, ARQ, ou `asyncio.create_task`
   se for single-instance).
3. Retorna imediatamente uma mensagem "commit feito, monitorando".

A background task:

1. Faz watch no Kubernetes API (ou polling com backoff).
2. Quando status vira `Ready: True`, lê `status.atProvider` (URL,
   credenciais, etc.).
3. Envia **mensagem proativa** de volta pro Telegram usando
   `TelegramTools` do Agno, com `chat_id` guardado na sessão.

```python
@tool(requires_confirmation=True)
async def provision_platform_instance(
    tenant_name: str,
    region: str,
    session_state: dict,  # injetado pelo Agno
) -> dict:
    # 1. Commit (síncrono, rápido)
    commit_info = commit_crossplane_manifest(tenant_name, region)

    # 2. Background task que notifica quando ficar Ready
    chat_id = session_state["telegram_chat_id"]
    await enqueue_provisioning_watch(
        resource_name=commit_info["resource_name"],
        resource_kind=commit_info["resource_kind"],
        namespace=commit_info["namespace"],
        notify_chat_id=chat_id,
        timeout_seconds=1800,  # 30 min
    )

    # 3. Retorno imediato
    return {
        "status": "provisioning",
        "commit": commit_info["commit_sha"],
        "estimated_minutes": "5-15",
    }
```

Watcher (mesmo processo ou worker separado):

```python
async def watch_and_notify(
    resource_name, resource_kind, namespace, notify_chat_id
):
    async with kubernetes_watch_client() as k8s:
        async for event in k8s.watch(
            api_version="platform.example.com/v1alpha1",
            kind=resource_kind,
            namespace=namespace,
            name=resource_name,
            timeout=1800,
        ):
            ready = next(
                (c for c in event.status.conditions if c.type == "Ready"),
                None,
            )
            if ready and ready.status == "True":
                url = event.status.atProvider.url
                await send_telegram_message(
                    chat_id=notify_chat_id,
                    text=(
                        f"✅ Instância {resource_name} pronta!\n\n"
                        f"Acesse em: {url}\n"
                        f"Use sua conta da empresa para autenticar."
                    ),
                )
                return
            if (
                ready
                and ready.status == "False"
                and ready.reason == "ReconcileError"
            ):
                await send_telegram_message(
                    chat_id=notify_chat_id,
                    text=(
                        f"❌ Falha provisionando {resource_name}:\n"
                        f"{ready.message}"
                    ),
                )
                return
```

### Padrão 3 — Event-driven via ArgoCD/Crossplane → webhook → agente

Mais maduro para produção (overkill no começo). ArgoCD notifications
ou controller customizado emite evento quando `PlatformInstance` muda
de status → webhook → enfileira mensagem pro usuário correto. Vale
considerar quando houver muitos provisionamentos concorrentes ou
múltiplos canais recebendo notificações.

---

## Permissões e segurança

- **GitHub PAT com escopo mínimo.** Fine-grained PAT, só no repo
  `aws-saas-platform`, só `Contents: write` (e `Pull requests: write`
  se for criar PRs). Nunca classic token com `repo` inteiro.
- **GitHub App > PAT** assim que possível. Token de instalação com
  TTL 1h, por-repo, revogação trivial. PyGithub suporta.
- **Branch protection no `main`.** Ideal: agente abre PR, merge
  condicionado a CI (lint YAML, validação schema Crossplane,
  `kubectl apply --dry-run`). Se commit direto em branch de staging
  que ArgoCD usa, ok — mas `main` produção precisa proteção.
- **Kubernetes RBAC pro watcher.** ServiceAccount com `get/watch/list`
  só no GVK dos `PlatformInstance`.
- **Validação de `tenant_name`.** Regex restrita, lista de palavras
  proibidas, checar duplicata antes de commit (evita erro 422
  confuso pro usuário).
- **Auditoria.** Cada `requires_confirmation` aprovado vira evento
  auditado no Postgres do Agno (tracing nativo). Quem pediu, quem
  confirmou, quando, qual commit.
- **Idempotência.** Telegram às vezes reentrega — tool deve detectar
  pedido duplicado e não criar duas instâncias.

---

## Integração com o stack atual (`aws-saas-platform`)

- **Templates Crossplane:** vivem no próprio repo, em
  `templates/platform-instance.yaml.j2`. Agente lê em runtime ou
  embute na imagem.
- **PAT/GitHub App credentials:** External Secrets Operator → AWS
  Secrets Manager → secret montado no pod do agente.
- **Watcher:** roda dentro do pod do AgentOS (asyncio task) ou como
  sidecar/job separado. Como agente já está no EKS, usa
  ServiceAccount do pod com **IRSA** — sem kubeconfig externo.
- **MCP fitness functions:** pós-deploy, agente pode chamar fitness
  functions OTel pra confirmar SLOs antes de declarar
  "pronta e acessível".
- **`waspctl`:** expor seu CLI como tools de leitura também —
  `waspctl tenant list/describe` viram tools de query.

---

## Esqueleto consolidado

```python
from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.tools import tool
from typing import Literal

@tool(requires_confirmation=True)
def provision_platform_instance(
    tenant_name: str,
    region: Literal["LATAM", "NA", "EU", "APAC"],
    tier: Literal["dev", "staging", "prod"] = "dev",
) -> dict:
    """Provisions a new platform instance via GitOps."""
    # validar → renderizar template → commitar → disparar watcher
    ...

@tool
def get_platform_instance_status(tenant_name: str, region: str) -> dict:
    """Reads current status of a platform instance from the cluster."""
    ...

@tool
def list_platform_instances(region: str | None = None) -> list[dict]:
    """Lists platform instances, optionally filtered by region."""
    ...

agent = Agent(
    model=Claude(id="claude-sonnet-4-5"),
    db=db,
    instructions=[
        "You are a platform engineer assistant for aws-saas-platform.",
        "When users ask to create instances, extract: tenant name, region, tier.",
        "Always confirm parameters before provisioning.",
        "After provisioning starts, tell the user you'll notify them when ready.",
        "Never generate Crossplane YAML yourself — use the provision tool.",
    ],
    tools=[
        provision_platform_instance,
        get_platform_instance_status,
        list_platform_instances,
    ],
    add_history_to_messages=True,
)
```

---

## Roadmap incremental

1. Tool `provision_platform_instance` rodando contra **repo de teste**,
   sem watcher ainda. Confirmação habilitada. Valida fluxo
   conversa → commit.
2. Adiciona watcher como `asyncio` task em-processo, contra cluster
   kind/minikube com Crossplane (mock provider). Mensagem proativa
   volta pro Telegram.
3. Substitui template hardcoded por **Jinja2** lendo do repo.
4. Migra PAT → **GitHub App**.
5. Deploy no EKS de verdade com External Secrets + IRSA.
6. (Futuro) Padrão 3 event-driven quando volume justificar.

---

## Decisões em aberto

- Commit direto em `main` numa branch de staging-gitops vs sempre
  abrir PR?
- Watcher in-process vs worker dedicado (ARQ/Celery)?
- Onde mora o template Jinja2 — embutido na imagem ou lido do repo
  em runtime?
- GitHub App desde o dia 1 ou PAT no MVP e migra depois?

## Referências

- GitHub MCP Server oficial:
  <https://github.com/github/github-mcp-server>
- PyGithub: <https://github.com/PyGithub/PyGithub>
- Agno MCP tools: <https://docs.agno.com/>
- Agno human-in-the-loop / `requires_confirmation`: docs Agno
- External Secrets Operator: <https://external-secrets.io/>
- IRSA (IAM Roles for Service Accounts): docs AWS EKS

# Validation paths

Três formas de validar o `wasp-agent`. Cada uma valida coisas diferentes — escolha conforme o que você mudou.

---

## A. Pipeline E2E — automatizado

`make e2e`. Valida o fluxo agente → Git → cluster com Crossplane, GitHub e Telegram simulados localmente.

| Componente | Substituto |
|---|---|
| Cluster Kubernetes | k3d **barebones** (só o CRD `Platform` aplicado) |
| Crossplane | `fake_reconciler` em `tests/e2e/conftest.py` (patcheia `status.Ready=True`) |
| GitHub | Container Gitea local |
| Telegram | `RecordingNotifier` (in-memory) |
| HTTP | `httpx.ASGITransport(app=main.app)` |

```bash
make k3d-up    # cluster + Platform CRD
make e2e
make k3d-down
```

CI: `.github/workflows/e2e.yaml` (sobe k3d ephemeral, sem precisar de `make k3d-up` manual).

`make k3d-up` **não** instala ArgoCD nem Crossplane — é o cluster mínimo para os testes E2E.

---

## B. Smoke test Telegram — manual, **sem cluster**

Valida o canal Telegram + auth multi-canal + comportamento do LLM. **Não exige cluster nem provisionamento real.**

O que esse smoke test cobre:

- Webhook do Telegram chega ao agente via ngrok
- Validação do `X-Telegram-Bot-Api-Secret-Token`
- Deep link `/start <token>` consome invite e autoriza o `chat_id`
- Auth guard em `provision_platform_instance` (allow para chat autorizado, deny silencioso para os demais)
- Agente processa e responde
- LLM segue o system prompt (em especial: pede confirmação antes de `provision_platform_instance`)
- Memória de sessão (`add_history_to_context=True`)
- Notifier Telegram escreve de volta no chat

### B.1. Setup de infraestrutura (uma vez por máquina)

Seguir [`telegram-local-dev.md`](telegram-local-dev.md):

1. Bot criado no `@BotFather`, com `TELEGRAM_TOKEN` no `.env`.
2. `TELEGRAM_WEBHOOK_SECRET_TOKEN` gerado e no `.env`.
3. `TELEGRAM_BOT_USERNAME` no `.env` — sem o `@`, ex: `wasp_local_bot`. Usado para montar o link `https://t.me/<bot>?start=<token>`.
4. ngrok rodando + webhook registrado no Telegram com path `/telegram/webhook`.

### B.2. Descobrir seu `user.id` do Telegram

Abrir [@userinfobot](https://t.me/userinfobot) e enviar qualquer mensagem. Anotar o `Id` numérico — é o `channel_id` do canal `tg`.

### B.3. Inicializar o agente

```bash
make run     # agente local na porta 7777
```

O `init_db()` cria as tabelas `auth_*` no `agent.db` na primeira inicialização. Deixar rodando em primeiro plano para acompanhar os logs.

### B.4. Setup de auth — escolher um dos dois fluxos

**Fluxo 1: bootstrap (primeiro deploy, tabela vazia)**

Em outro terminal:

```bash
make admin-bootstrap NAME="Você" CHANNEL=tg ID=<seu user.id>
```

Saída esperada: `Bootstrapped user: <uuid>`. Falha se já existir qualquer usuário — nesse caso, use o Fluxo 2 ou apague `agent.db` (ver B.7).

**Fluxo 2: invite + deep link (admin já existe; novo usuário entrando)**

```bash
make admin-invite NAME="Você"
```

Saída inclui `Token: <urlsafe>` e `Link: https://t.me/<bot>?start=<token>`. Clicar no link no Telegram. O bot deve responder:

```
Bem-vindo, Você. Você está autorizado a usar o wasp-agent.
```

Se aparecer `Link inválido ou expirado.`, verificar:

- TTL expirou (default 1h, ajustável via `WASP_AGENT_INVITE_TTL_HOURS`)
- Token já consumido — gerar novo invite
- `TELEGRAM_BOT_USERNAME` no `.env` aponta para o bot certo

Confirmar a inserção:

```bash
make admin-list
```

Deve listar `tg`, seu `user.id`, e o `display_name`.

### B.5. Roteiro do smoke test

No chat do Telegram:

1. `"oi"` → bot responde (chat normal).
2. `"Meu nome é João."` depois `"Qual é o meu nome?"` → bot lembra (memória de sessão, `add_history_to_context=True`).
3. `"Criar uma plataforma chamada test"` → bot **pede confirmação**, não chama a tool sozinho.
4. `"não, cancela"` → bot não chama a tool.

Os passos 1–4 cobrem o que muda com mais frequência (system prompt, wiring do Telegram, formato de respostas, auth allow path). Se você **confirmar** o pedido no passo 3, a tool roda de verdade — sem cluster nem GitHub configurado, isso falha. Para o smoke test puro, basta recusar.

### B.6. Verificar o auth deny path (opcional, recomendado depois de mudar `provision.py` ou `auth.py`)

Pedir a alguém com outro `chat_id` (não autorizado) que envie qualquer mensagem ao bot. Resultado esperado:

- O LLM responde normalmente em mensagens conversacionais.
- Mas se essa pessoa pedir `"criar plataforma X"` e **confirmar**, a tool retorna `{"status": "unauthorized", "message": "Acesso negado."}`. O bot relata isso ao usuário.

Validar nos logs do `make run` (ou em `logs/wasp.jsonl` se `LOG_FILE` estiver setado):

```bash
grep "auth denied" logs/wasp.jsonl  # ou stdout do agente
```

Deve aparecer `auth denied: channel=tg channel_id=<outro id>`.

Se `PROMETHEUS_METRICS_ACTIVE=true`:

```bash
curl -s http://localhost:7777/telemetry/prometheus | grep wasp_auth_denied_total
```

Deve incrementar `wasp_auth_denied_total{channel="tg",reason="unknown_identity"}`.

### B.7. Reset de estado (refazer bootstrap)

`make admin-bootstrap` recusa rodar com a tabela populada. Para zerar:

```bash
rm agent.db
make run    # init_db recria as tabelas vazias
make admin-bootstrap NAME="..." CHANNEL=tg ID=<id>
```

`agent.db` guarda também a memória das sessões agno — apagar perde todo o histórico de conversas anteriores. Em produção, prefira `make admin-revoke` + novo `make admin-invite`.

---

## C. Validar Prometheus — independente

Ortogonal a A e B. Não exige cluster nem Telegram.

```bash
# Standalone
make smoke-prometheus

# Integrado (com o agente rodando)
PROMETHEUS_METRICS_ACTIVE=true make run
curl http://localhost:7777/telemetry/prometheus | grep agent_
```

---

## D. Local chat — manual, **sem Telegram**

Equivalente ao path B (smoke Telegram), mas usando `curl` / `scripts/local-chat`. Ver [`local-chat.md`](local-chat.md).

Útil para iteração rápida em system prompt, memória de sessão e fluxo de confirmação sem montar ngrok + bot.

```bash
unset TELEGRAM_TOKEN
make run

# em outro terminal
make local-chat
```

Para o happy-path com notificação `Ready` (passos 4-5 do roteiro chegam a `provision_platform_instance` rodando de verdade), o setup de infra é o do apêndice abaixo.

---

## Apêndice: validação completa do ciclo GitOps (raro)

Quando você mudou `wasp/provision.py`, `wasp/watcher.py` ou a Composition do Crossplane, pode querer validar o ciclo real: Telegram → commit em `wasp-gitops` → ArgoCD sync → Crossplane reconcile → notificação `Ready` no Telegram.

Passos:

1. Subir cluster com ArgoCD + Crossplane + Application `wasp-gitops` — seguir [`k3d-argocd-wasp-gitops.md`](k3d-argocd-wasp-gitops.md).
2. Executar o smoke test (B), mas dessa vez **confirmar** o provisionamento.
3. Aguardar a notificação de `Ready` chegar no Telegram.

Não é smoke test — é validação pesada, reservada para mudanças na camada de provisionamento.

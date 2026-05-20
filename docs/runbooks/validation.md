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

Valida o canal Telegram + comportamento do LLM. **Não exige cluster nem provisionamento real.**

O que esse smoke test cobre:
- Webhook do Telegram chega ao agente via ngrok
- Agente processa e responde
- LLM segue o system prompt (em especial: pede confirmação antes de `provision_platform_instance`)
- Memória de sessão (`add_history_to_context=True`)
- Notifier Telegram escreve de volta no chat

Pré-requisito: bot Telegram + ngrok + webhook — seguir [`telegram-local-dev.md`](telegram-local-dev.md).

Execução:

```bash
make run     # agente local na porta 7777
```

Roteiro sugerido no Telegram:

1. Mensagem qualquer (`"oi"`) → bot responde.
2. `"Meu nome é João."` depois `"Qual é o meu nome?"` → bot lembra (memória de sessão).
3. `"Criar uma plataforma chamada test"` → bot **pede confirmação**, não chama a tool sozinho.
4. Recusar (`"não, cancela"`) → bot não chama a tool.

Esse roteiro cobre o que muda com mais frequência (system prompt, wiring do Telegram, formato de respostas). Se você **confirmar** o pedido no passo 3, a tool roda de verdade — sem cluster nem GitHub configurado, isso falha. Para o smoke test puro, basta recusar.

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

## Apêndice: validação completa do ciclo GitOps (raro)

Quando você mudou `tools/provision.py`, `tools/watcher.py` ou a Composition do Crossplane, pode querer validar o ciclo real: Telegram → commit em `wasp-gitops` → ArgoCD sync → Crossplane reconcile → notificação `Ready` no Telegram.

Passos:

1. Subir cluster com ArgoCD + Crossplane + Application `wasp-gitops` — seguir [`k3d-argocd-wasp-gitops.md`](k3d-argocd-wasp-gitops.md).
2. Executar o smoke test (B), mas dessa vez **confirmar** o provisionamento.
3. Aguardar a notificação de `Ready` chegar no Telegram.

Não é smoke test — é validação pesada, reservada para mudanças na camada de provisionamento.

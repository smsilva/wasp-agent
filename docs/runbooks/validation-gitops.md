# Validação completa do ciclo GitOps (raro)

Quando você mudou `wasp/provision.py`, `wasp/watcher.py` ou a Composition do Crossplane, valide o ciclo real: Telegram → commit em `wasp-gitops` → ArgoCD sync → Crossplane reconcile → notificação `Ready` no Telegram.

> Não é smoke test — é validação pesada (~10–15 min). Reserve para mudanças na camada de provisionamento.

## Pré-requisitos adicionais (além do setup Telegram)

- `k3d`, `helm`, `kubectl` instalados
- `~/git/kubernetes` clonado: `git clone https://github.com/smsilva/kubernetes ~/git/kubernetes`
- `GH_PAT` no `.env` com `Contents: write` em `smsilva/wasp-gitops` — ver [`github-pat-setup.md`](github-pat-setup.md)
- ngrok rodando + webhook registrado (ver [`telegram-local-dev.md`](telegram-local-dev.md))

## E.1. Subir cluster GitOps

```bash
make gitops-up
```

Aguardar ~5–10 min. Cria o cluster `k3s-default` com ArgoCD, Crossplane, e a Application `wasp-gitops` apontando para o branch `dev` de `smsilva/wasp-gitops`.

Verificar:

```bash
kubectl get pods --all-namespaces           # todos Running/Completed
kubectl get application wasp-gitops -n argocd   # Synced / Healthy
```

## E.2. Auth bootstrap

```bash
make admin-bootstrap NAME="<nome>" CHANNEL=tg ID=<seu_chat_id>
make admin-list    # confirma inserção
```

Para descobrir seu `chat_id`: enviar qualquer mensagem ao bot e ler nos logs do `make run` a linha `Processing message from user <chat_id>`, ou usar [@userinfobot](https://t.me/userinfobot).

## E.3. Iniciar o agente

```bash
make run
```

Verificar webhook sem erros:

```bash
source .env
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo" \
  | python3 -m json.tool | grep -E '"url"|"last_error"'
```

## E.4. Executar o ciclo completo

No Telegram:

1. Enviar `"criar uma plataforma chamada <nome>"` → bot pede confirmação.
2. Responder `"sim"` → bot chama `provision_platform_instance`; commit aparece no branch `dev` de `smsilva/wasp-gitops`.

Verificar o commit:

```bash
source .env
curl -s -H "Authorization: Bearer ${GH_PAT}" \
  "https://api.github.com/repos/smsilva/wasp-gitops/commits?sha=dev&per_page=1" \
  | python3 -m json.tool | grep '"message"'
```

Esperado: `"feat(tenants): provision <nome>"`.

## E.5. Acompanhar ArgoCD sync e Crossplane reconcile

```bash
# ArgoCD sync (automático, alguns segundos após o commit)
kubectl get application wasp-gitops -n argocd

# Crossplane reconcile
kubectl get platform <nome>
```

Aguardar `READY=True` no Platform. Tempo típico do ciclo após confirmação no Telegram: **~2 minutos**.

## E.6. Notificação Ready

Quando `READY=True`, o watcher envia automaticamente no Telegram:

```
Plataforma '<nome>' está pronta.
- us-east-1: https://gateway.us-east-1.<nome>.wasp.silvios.me
```

## E.7. Limpar

```bash
make gitops-down
```

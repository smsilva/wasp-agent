# Telegram Full GitOps Runbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Executar o fluxo completo Telegram → GitOps → Ready e expandir o Apêndice de `validation.md` com passos detalhados e critérios de verificação.

**Architecture:** Execução sequencial de comandos no ambiente local; saídas observadas servem como base para o texto do runbook. Nenhum código de produção é alterado — apenas `docs/runbooks/validation.md`.

**Tech Stack:** k3d, ArgoCD, Crossplane, kubectl, make, Python (wasp-agent), Telegram Bot API, GitHub API.

---

### Task 1: Auth bootstrap

**Files:**
- Read: `docs/runbooks/auth-admin.md` (referência)

- [ ] **Step 1: Verificar que a tabela de auth está vazia**

```bash
make admin-list
```

Esperado: `(no identities)`

- [ ] **Step 2: Descobrir o chat_id do Telegram**

Nos logs do `make run` (pane do servidor), procurar:

```
INFO Processing message from user <chat_id>
```

O chat_id está nos logs da última mensagem enviada ao bot. Alternativamente, abrir [@userinfobot](https://t.me/userinfobot) no Telegram e enviar qualquer mensagem — ele retorna o `Id` numérico.

- [ ] **Step 3: Executar o bootstrap**

```bash
make admin-bootstrap NAME="Silvio" CHANNEL=tg ID=<chat_id>
```

Esperado: `Bootstrapped user: <uuid>`

- [ ] **Step 4: Confirmar inserção**

```bash
make admin-list
```

Esperado: linha com `tg`, o `chat_id` usado, e `Silvio`.

- [ ] **Step 5: Anotar o comando exato para o runbook**

Copiar o comando do Step 3 com o formato final: `make admin-bootstrap NAME="<nome>" CHANNEL=tg ID=<chat_id>`.

---

### Task 2: Subir cluster GitOps

**Files:**
- Read: `docs/runbooks/k3d-argocd-wasp-gitops.md` (referência)

- [ ] **Step 1: Verificar pré-requisitos**

```bash
k3d version && helm version --short && kubectl version --client --short
```

Esperado: versões exibidas sem erro.

- [ ] **Step 2: Verificar repositório kubernetes clonado**

```bash
ls ~/git/kubernetes/lab/argo/argocd/run
```

Se não existir: `git clone https://github.com/smsilva/kubernetes ~/git/kubernetes`

- [ ] **Step 3: Verificar GH_PAT no .env**

```bash
grep "^GH_PAT=" .env | sed 's/=.*/=<set>/'
```

Esperado: `GH_PAT=<set>`. Se ausente, seguir `docs/runbooks/github-pat-setup.md`.

- [ ] **Step 4: Subir o cluster**

```bash
make gitops-up
```

Este comando executa: `k3d cluster delete k3s-default`, `k3d cluster create k3s-default`, ArgoCD, Crossplane, Application `wasp-gitops`. Aguardar conclusão (~3–5 min).

- [ ] **Step 5: Verificar pods**

```bash
kubectl get pods --all-namespaces
```

Esperado: todos os pods em `Running` ou `Completed`.

- [ ] **Step 6: Verificar Application ArgoCD**

```bash
argocd app get wasp-gitops --server localhost:9443 --insecure 2>/dev/null \
  || kubectl get application wasp-gitops --namespace argocd
```

Esperado: `Sync Status: Synced`, `Health Status: Healthy`.

- [ ] **Step 7: Anotar tempo de conclusão do make gitops-up para o runbook**

Registrar o tempo total e qualquer output relevante.

---

### Task 3: Verificar agente rodando

**Files:**
- Read: pane do servidor tmux

- [ ] **Step 1: Confirmar agente na porta 7777**

```bash
curl -s http://localhost:7777/health 2>/dev/null || curl -s http://localhost:7777/
```

Se não estiver rodando:

```bash
make run
```

- [ ] **Step 2: Confirmar webhook registrado**

```bash
source .env
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo" \
  | python3 -m json.tool | grep -E '"url"|"last_error"'
```

Esperado: `"url"` aponta para ngrok + `/telegram/webhook`, sem `last_error_message`.

---

### Task 4: Executar smoke test com confirmação

**Files:**
- Read: pane tmux do servidor (logs em tempo real)

- [ ] **Step 1: Enviar mensagem inicial no Telegram**

No chat do bot, enviar: `"oi"`. Bot deve responder normalmente.

- [ ] **Step 2: Solicitar criação de plataforma**

Enviar: `"criar uma plataforma chamada smoke-test-01"`.

Bot deve pedir confirmação sem chamar a tool diretamente.

- [ ] **Step 3: Confirmar**

Enviar: `"sim"`.

Nos logs do servidor, deve aparecer:
```
INFO Processing message from user <chat_id>
```
Seguido de chamada à tool `provision_platform_instance`.

- [ ] **Step 4: Verificar commit no wasp-gitops**

```bash
source .env
curl -s \
  -H "Authorization: Bearer ${GH_PAT}" \
  "https://api.github.com/repos/smsilva/wasp-gitops/commits?per_page=1" \
  | python3 -m json.tool | grep '"message"'
```

Esperado: commit `feat(tenants): provision smoke-test-01`.

- [ ] **Step 5: Acompanhar ArgoCD sync**

```bash
watch kubectl get application wasp-gitops --namespace argocd
```

Aguardar `Sync Status: Synced` com o novo commit (~3 min após o commit).

- [ ] **Step 6: Acompanhar Crossplane reconcile**

```bash
watch kubectl get platform smoke-test-01 2>/dev/null \
  || kubectl get platforms --all-namespaces
```

Aguardar `Ready=True`.

- [ ] **Step 7: Confirmar notificação Ready no Telegram**

O watcher deve detectar `Ready=True` e enviar mensagem no Telegram informando que a plataforma está pronta. Anotar o texto exato da mensagem para o runbook.

- [ ] **Step 8: Registrar tempo total do ciclo**

Tempo entre a confirmação no Telegram e a notificação Ready.

---

### Task 5: Expandir Apêndice em validation.md

**Files:**
- Modify: `docs/runbooks/validation.md` — seção "Apêndice"

- [ ] **Step 1: Abrir o arquivo e localizar o Apêndice**

O Apêndice está no final de `docs/runbooks/validation.md` (linha ~186).

- [ ] **Step 2: Substituir o Apêndice atual pelo expandido**

Substituir os 3 bullets existentes pela estrutura abaixo, preenchendo os valores reais observados nas Tasks 1–4:

```markdown
## Apêndice: validação completa do ciclo GitOps (raro)

Quando você mudou `wasp/provision.py`, `wasp/watcher.py` ou a Composition do Crossplane,
valide o ciclo real: Telegram → commit em `wasp-gitops` → ArgoCD sync →
Crossplane reconcile → notificação Ready no Telegram.

> Não é smoke test — é validação pesada (~10–20 min). Reserve para mudanças na camada de provisionamento.

### Pré-requisitos adicionais (além de B.1)

- `k3d`, `helm`, `kubectl` instalados
- `~/git/kubernetes` clonado: `git clone https://github.com/smsilva/kubernetes ~/git/kubernetes`
- `GH_PAT` no `.env` com `Contents: write` em `smsilva/wasp-gitops` — ver [`github-pat-setup.md`](github-pat-setup.md)
- ngrok rodando + webhook registrado (B.1)

### 1. Subir cluster GitOps

```bash
make gitops-up
```

Aguardar ~3–5 min. Verifica:

```bash
kubectl get pods --all-namespaces          # todos Running/Completed
kubectl get application wasp-gitops -n argocd  # Synced / Healthy
```

### 2. Auth bootstrap

```bash
make admin-bootstrap NAME="<nome>" CHANNEL=tg ID=<seu_chat_id>
make admin-list    # confirma inserção
```

Para descobrir seu `chat_id`: enviar qualquer mensagem ao bot e ler nos logs do `make run` a linha `Processing message from user <chat_id>`, ou usar [@userinfobot](https://t.me/userinfobot).

### 3. Iniciar o agente

```bash
make run
```

Verificar webhook:

```bash
source .env
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo" \
  | python3 -m json.tool | grep -E '"url"|"last_error"'
```

Sem `last_error_message` = ok.

### 4. Executar o ciclo completo

No Telegram:

1. `"oi"` → bot responde (canal funcionando).
2. `"criar uma plataforma chamada <nome>"` → bot pede confirmação.
3. `"sim"` → bot chama `provision_platform_instance`; commit aparece em `smsilva/wasp-gitops`.

Acompanhar:

```bash
# ArgoCD sync (~ 3 min após o commit)
watch kubectl get application wasp-gitops --namespace argocd

# Crossplane reconcile
watch kubectl get platform <nome>
```

### 5. Notificação Ready

Quando `kubectl get platform <nome>` mostrar `Ready=True`, o watcher envia mensagem no Telegram informando que a plataforma está pronta.

Tempo típico do ciclo: **<PREENCHER_COM_TEMPO_OBSERVADO>** (confirmação → notificação Ready).

### 6. Limpar

```bash
make gitops-down
```
```

- [ ] **Step 3: Preencher o tempo típico do ciclo**

Usar o valor anotado na Task 4, Step 8.

- [ ] **Step 4: Verificar que o Markdown renderiza corretamente**

```bash
python3 -c "
import re, sys
content = open('docs/runbooks/validation.md').read()
print('OK' if '### 1. Subir cluster GitOps' in content else 'ERRO: seção não encontrada')
"
```

Esperado: `OK`

---

### Task 6: Commit final

**Files:**
- Commit: `docs/runbooks/validation.md`

- [ ] **Step 1: Verificar diff**

```bash
git diff docs/runbooks/validation.md
```

Confirmar que apenas o Apêndice foi modificado.

- [ ] **Step 2: Commitar**

```bash
git add docs/runbooks/validation.md
git commit -m "docs(runbooks): expandir Apêndice GitOps completo em validation.md"
```

- [ ] **Step 3: Derrubar o cluster**

```bash
make gitops-down
```

---

## Self-Review

- **Cobertura do spec:** todos os pré-requisitos, sequência, critérios de verificação e limpeza estão cobertos nas Tasks 1–6. ✓
- **Placeholders:** o único placeholder intencional é `<PREENCHER_COM_TEMPO_OBSERVADO>` — será preenchido com dado real na execução. ✓
- **Consistência:** comandos usam `make gitops-up/down`, `make admin-bootstrap`, `make run` consistentemente com o Makefile. ✓

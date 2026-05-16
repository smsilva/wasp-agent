# k3d + ArgoCD + wasp-gitops

Como criar um cluster k3d com ArgoCD instalado e a Application `wasp-gitops` apontando para o repositório GitOps do Wasp.

---

## Pré-requisitos

- `k3d` instalado
- `helm` instalado
- `kubectl` instalado
- Repositório clonado localmente:

```bash
git clone https://github.com/smsilva/kubernetes ~/git/kubernetes
```

---

## 1. Criar o cluster e instalar o ArgoCD

Script: `/home/silvios/git/kubernetes/lab/argo/argocd/run`

```bash
cd ~/git/kubernetes/lab/argo/argocd

bash run
```

O script `run` executa em sequência:
1. `k3d-cluster-creation.sh` — cria o cluster com 3 servidores, ports 9080/9443 expostos
2. `argocd-install.sh` — instala ArgoCD via Helm e aguarda todos os deployments ficarem Available
3. `argocd-notification.sh` — configura notificações
4. `argocd-get-initial-password.sh` — exibe a senha inicial do admin

---

## 2. Instalar o Crossplane

Script: `/home/silvios/git/kubernetes/lab/argo/argocd/crossplane-install.sh`

```bash
cd ~/git/kubernetes/lab/argo/argocd

bash crossplane-install.sh
```

Instala o Crossplane 2.2.1 via Helm no namespace `crossplane-system` e aguarda os deployments ficarem Available.

---

## 3. Aplicar a Application wasp-gitops

O manifesto está em `docs/runbooks/wasp-gitops-application.yaml` neste repositório (`wasp-agent`).

```bash
kubectl apply \
  --filename ~/git/wasp-agent/docs/runbooks/wasp-gitops-application.yaml
```

Aponta para:

| Campo | Valor |
|-------|-------|
| `repoURL` | `https://github.com/smsilva/wasp-gitops.git` |
| `targetRevision` | `dev` |
| `path` | `infrastructure/tenants` |
| `destination.name` | `in-cluster` |
| `destination.namespace` | `infra` |
| `automated.prune` | `false` |
| `automated.selfHeal` | `true` |

---

## 4. Verificar sincronização

```bash
argocd app get wasp-gitops
```

Ou via UI: acesse `https://localhost:9443`, faça login com `admin` e a senha exibida no passo 1.

---

## Remover o cluster

```bash
k3d cluster delete --all
```

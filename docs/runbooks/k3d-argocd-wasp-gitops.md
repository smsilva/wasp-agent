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

O manifesto está em `manifests/argocd/wasp-gitops-application.yaml` neste repositório (`wasp-agent`).

```bash
kubectl apply \
  --filename ~/git/wasp-agent/manifests/argocd/wasp-gitops-application.yaml
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

## 4. Instalar o Kubernetes provider do Crossplane

O Crossplane precisa do provider `upbound/provider-kubernetes` para criar os objetos (`Object`) que a Composition usa.

O manifesto inclui um `DeploymentRuntimeConfig` que pina o nome do `ServiceAccount` do provider para `provider-kubernetes` — sem isso, o SA é gerado em runtime com um hash que muda a cada reinstalação e quebra o `ClusterRoleBinding`.

```bash
kubectl apply \
  --filename manifests/crossplane/providers/kubernetes.yaml
```

Aguardar o provider ficar healthy:

```bash
kubectl wait provider/provider-kubernetes \
  --for=condition=Healthy \
  --timeout=120s
```

Aplicar o `ProviderConfig` (`InjectedIdentity`) e o `ClusterRoleBinding` que dá `cluster-admin` ao SA pinado:

```bash
kubectl apply \
  --filename manifests/crossplane/providerconfigs/kubernetes.yaml
```

---

## 5. Instalar a function-patch-and-transform

Crossplane v2 removeu o modo `spec.resources` (patch-and-transform legacy) das Compositions. A Composition de Platform usa `spec.mode: Pipeline` com `function-patch-and-transform`, que precisa estar instalada antes.

```bash
kubectl apply \
  --filename manifests/crossplane/functions/patch-and-transform.yaml
```

Aguardar a function ficar healthy:

```bash
kubectl wait function/function-patch-and-transform \
  --for=condition=Healthy \
  --timeout=120s
```

---

## 6. Aplicar os manifestos Crossplane locais

XRD em `apiextensions.crossplane.io/v2` (`scope: Cluster`) e Composition em modo Pipeline.

```bash
kubectl apply \
  --filename manifests/crossplane/xrd/platform.yaml

kubectl apply \
  --filename manifests/crossplane/compositions/platform.yaml
```

---

## 7. Verificar sincronização e testar

```bash
argocd app get wasp-gitops
```

Ou via UI: acesse `https://localhost:9443`, faça login com `admin` e a senha exibida no passo 1.

Para testar o ciclo completo sem o wasp-agent, aplique a Platform instance de exemplo:

```bash
kubectl apply \
  --filename manifests/tenants/example.yaml
```

Verificar o ConfigMap criado pelo Crossplane:

```bash
kubectl get configmap example --namespace example --output yaml
```

---

## Remover o cluster

```bash
k3d cluster delete --all
```

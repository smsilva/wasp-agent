# Helm Chart — distribuição do wasp-agent em clusters Kubernetes

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

Hoje o `wasp-agent` roda localmente via `make run` ou via `make e2e` em k3d. Não existe mecanismo formal de distribuição para clusters Kubernetes de terceiros. Um Helm chart resolve isso: empacota o agente com seus requisitos de runtime (segredos, config, RBAC, networking) em um artefato versionado e instalável via `helm install`.

O agente provisiona infraestrutura via GitOps e recebe comandos por Telegram — tem requisitos não triviais de configuração (tokens, PATs, URLs de webhook) que um chart pode encapsular com defaults razoáveis e validação de valores.

## O que um chart precisa cobrir

### Workload

- `Deployment` com `replicas: 1` (o agente é stateful por sessão — múltiplas réplicas requerem session affinity ou refactor).
- `livenessProbe` e `readinessProbe` via `/health` (ou endpoint equivalente — verificar se existe, adicionar se não).
- `resources.requests/limits` para CPU e memória — defaults conservadores.
- `securityContext`: `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`.

### Configuração

- `ConfigMap` para variáveis não-sensíveis (`WASP_AGENT_*`, `OTEL_*`, `PROMETHEUS_METRICS_ACTIVE`).
- `Secret` para credenciais (`TELEGRAM_BOT_TOKEN`, `GH_PAT`, `ANTHROPIC_API_KEY`). O chart **não deve embutir segredos** — referenciar via `existingSecret` ou integração com External Secrets Operator.
- `values.yaml` com todas as variáveis documentadas e defaults seguros.

### Networking

- `Service` tipo `ClusterIP` por padrão.
- `Ingress` opcional (habilitado via `ingress.enabled: true`) com suporte a `className`, `annotations` (cert-manager, nginx), e TLS.
- Telegram exige endpoint HTTPS público para webhook — o chart deve documentar esse requisito explicitamente.

### RBAC

O agente interage com o cluster via `kubectl`/client-go (se e quando implementado):

- `ServiceAccount` dedicado.
- `ClusterRole` / `Role` com permissões mínimas — apenas o que o agente precisa para provisionar (CRDs do Crossplane, etc.).
- `ClusterRoleBinding` / `RoleBinding`.

### Observabilidade

- Anotações Prometheus padrão no `Pod`: `prometheus.io/scrape: "true"`, `prometheus.io/port`, `prometheus.io/path: /telemetry/prometheus`.
- Opcional: `ServiceMonitor` (Prometheus Operator) habilitado via `metrics.serviceMonitor.enabled`.

### Persistência

- SQLite (`wasp/auth.db`) precisa de `PersistentVolumeClaim` se o pod reiniciar e dados de auth não podem ser perdidos.
- Alternativa: externalizar auth para Postgres (spec separado) e manter o chart stateless.
- Para v1 do chart: `PVC` opcional com `persistence.enabled: true`; default `false` com aviso no NOTES.txt.

## Estrutura de diretórios

```
charts/wasp-agent/
  Chart.yaml
  values.yaml
  values.schema.json       ← validação de valores obrigatórios
  templates/
    deployment.yaml
    service.yaml
    configmap.yaml
    secret.yaml            ← apenas se não usar existingSecret
    serviceaccount.yaml
    rbac.yaml
    ingress.yaml
    pvc.yaml
    hpa.yaml               ← opcional, HorizontalPodAutoscaler
    _helpers.tpl
    NOTES.txt
  .helmignore
```

## values.yaml — estrutura mínima

```yaml
image:
  repository: ghcr.io/org/wasp-agent
  tag: ""                  # default: .Chart.AppVersion
  pullPolicy: IfNotPresent

replicaCount: 1

config:
  logLevel: INFO
  prometheusMetricsActive: false
  otelExporterEndpoint: ""

telegram:
  existingSecret: ""       # nome do Secret com TELEGRAM_BOT_TOKEN
  webhookUrl: ""           # obrigatório; validado em values.schema.json

github:
  existingSecret: ""       # nome do Secret com GH_PAT

anthropic:
  existingSecret: ""       # nome do Secret com ANTHROPIC_API_KEY

ingress:
  enabled: false
  className: ""
  annotations: {}
  host: ""
  tls: []

persistence:
  enabled: false
  storageClass: ""
  size: 1Gi

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi

metrics:
  serviceMonitor:
    enabled: false

serviceAccount:
  create: true
  annotations: {}
```

## Versionamento e distribuição

### OCI registry (recomendado)

```bash
helm package charts/wasp-agent
helm push wasp-agent-*.tgz oci://ghcr.io/org/charts
```

Instalação:
```bash
helm install wasp-agent oci://ghcr.io/org/charts/wasp-agent \
  --version 0.1.0 \
  --values my-values.yaml
```

### GitHub Pages (alternativa clássica)

`cr` (chart-releaser) + GitHub Actions gera index e hospeda em `gh-pages`.

### Assinatura

`helm package --sign` com GPG, ou usar COSIGN após o push para OCI — conecta com `2026-05-26-supply-chain-security.md`.

## Conexão com outros specs

- **Supply Chain (`2026-05-26-supply-chain-security.md`):** assinar a imagem e o chart com COSIGN; gerar SBOM da imagem com `syft`. O chart distribui a imagem — mesma cadeia.
- **SBOM (`2026-05-26-sbom.md`):** `syft` pode gerar SBOM da imagem base usada no chart.
- **Snyk IaC (`2026-05-26-code-quality-security-scanning.md`):** `snyk iac test charts/wasp-agent/templates/` escaneia os templates antes do release.
- **EU AI Act / CRA (`2026-05-26-eu-ai-act.md`):** se o chart for distribuído publicamente, CRA aplica — o chart é o veículo de distribuição do produto.
- **DORA Metrics (`2026-05-26-dora-metrics.md`):** versão do chart publicada = evento de deploy mensurável para DF e LT.

## Decisões abertas

1. **Stateful vs stateless:** PVC para SQLite ou migrar auth para Postgres externo? PVC é mais simples para v1; Postgres é necessário para HA.
2. **Multi-canal no chart:** hoje Telegram; futuramente Discord/Slack. O chart deve parametrizar por canal ou ter um `values.yaml` por canal?
3. **RBAC scope:** o agente precisa de permissões de cluster hoje? Se não, omitir `ClusterRole` na v1 e adicionar quando necessário.
4. **Namespace dedicado:** chart deve criar namespace ou assumir que já existe? Convenção Helm: não criar namespace no chart — documentar em NOTES.txt.

## Armadilhas

- **Segredos no `values.yaml`.** Nunca colocar valores de secret em `values.yaml` — só referências a `existingSecret`. Documentar no README do chart.
- **`latest` como tag padrão.** Imagem sem tag fixa impede rollback determinístico. Default deve ser `appVersion` do `Chart.yaml`.
- **`readOnlyRootFilesystem` quebrando SQLite.** Se persistência estiver habilitada, o mount do PVC precisa estar em path gravável com `readOnlyRootFilesystem: true` — outros paths são somente-leitura.
- **Webhook sem TLS válido.** Telegram rejeita webhooks com certificado inválido. NOTES.txt deve avisar explicitamente.
- **HPA com `replicas: 1` stateful.** Escalar horizontalmente sem session affinity perde contexto de conversa. HPA só faz sentido após refactor de estado para store externo.

## Fora de escopo desta nota

- Operator Kubernetes para gestão de ciclo de vida avançado (upgrades automáticos, CRD do agente).
- Multi-tenant (um chart, múltiplas instâncias por namespace) — requer refactor de auth.
- Helm test (`helm test`) — verificação pós-install.

## Próximo passo

Promover a Draft quando houver decisão de containerizar o agente (Dockerfile). O chart depende da imagem — bloqueia nessa dependência. Ação preparatória: definir o `values.yaml` mínimo e `values.schema.json` antes de escrever os templates.

## Referências

- [Helm best practices](https://helm.sh/docs/chart_best_practices/)
- [values.schema.json](https://helm.sh/docs/topics/charts/#schema-files) — validação de valores
- [chart-releaser](https://github.com/helm/chart-releaser) — distribuição via GitHub Pages
- [Helm OCI support](https://helm.sh/docs/topics/registries/)
- [External Secrets Operator](https://external-secrets.io/) — integração com Vault, AWS SM, GCP SM
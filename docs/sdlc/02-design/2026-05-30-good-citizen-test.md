# Good Citizen Test — Especificação para o `wasp-agent`

> Documento de handoff para o agente continuar a implementação no projeto `wasp-agent`.
> Objetivo: transformar o conceito de "good citizen test" em um checklist executável,
> ancorado na abordagem de **Production Readiness Review (PRR)** descrita no
> *Google SRE Book* (cap. 32 — *The Evolving SRE Engagement Model*).

---

## 1. Contexto e objetivo

Toda aplicação nova que pretende entrar nos nossos clusters Kubernetes (EKS) deve passar
por um **Good Citizen Test**: uma avaliação automatizada que verifica se o serviço se
comporta como um "bom cidadão" no cluster antes de ganhar acesso à esteira de deploy.

A inspiração direta é o **PRR do SRE**: em vez de um review manual e pontual feito por uma
pessoa, cristalizamos as perguntas do PRR em **fitness functions** atômicas e disparáveis
(CLI + CI), no sentido do *Building Evolutionary Architectures*. O teste deve dar **feedback
cedo** (rodando localmente) e ser **incorporável ao CI/CD** como gate.

Princípio inegociável: o teste **não promete o que não consegue verificar**. Cada check
declara explicitamente *como* é verificado (ver tiers abaixo).

### O que NÃO é
- Não é um linter de YAML genérico (isso já existe — ver §6, "wrap, não reimplemente").
- Não é um bloqueio rígido sem escape. Serviços legados/de terceiros que não podemos
  mudar são acomodados via **registro de exceções** (§5), que vira conhecimento de incidente.
- Não é um score único de marketing. Ver modelo de pontuação (§4).

---

## 2. Princípio orientador: Production Readiness Review

O PRR avalia um serviço em dimensões operacionais antes do onboarding. Adaptamos as
dimensões clássicas para o nosso contexto (EKS, Istio, ArgoCD, ALB, Cognito, DynamoDB,
microsserviços FastAPI, GitOps + Crossplane) e — onde possível — tornamos cada dimensão
**mecanicamente testável**.

Mapeamento PRR → dimensões do Good Citizen Test:

| Dimensão PRR (SRE)              | Dimensão Good Citizen        | Seção |
|---------------------------------|------------------------------|-------|
| Monitoring & alerting           | Observabilidade              | §3.2  |
| Capacity & performance          | Recursos & scheduling        | §3.3  |
| Failure modes & dependencies    | Dependências & resiliência   | §3.6  |
| Configuration & change mgmt     | Configuração & 12-factor     | §3.5  |
| Release & rollback              | Release & rollback           | §3.7  |
| Security                        | Segurança                    | §3.4  |
| (lifecycle implícito)           | Health & ciclo de vida       | §3.1  |
| Docs, ownership, on-call        | Ownership & documentação     | §3.8  |

---

## 3. Modelo de execução: dois tiers

Cada check pertence a um tier que define **como** ele é verificado. O agente deve marcar
isso no metadado de cada check.

- **`static`** — inspeção dos manifests/Helm/kustomize renderizados. Barato, roda
  pre-merge, sem cluster. Só afirma que algo foi *declarado*.
- **`behavioral`** — sobe o serviço em namespace efêmero (kind local ou namespace
  descartável no EKS) e observa o comportamento real (ex.: `curl /metrics`, teste de
  `SIGTERM`). Mais caro, roda em estágio posterior do CI ou sob demanda.
- **`attestation`** — não verificável por máquina; o time **declara** e assina (ex.:
  statelessness, runbook existe). Fica registrado e auditável.

> Regra de ouro: a CLI local roda o tier `static` (feedback instantâneo). O tier
> `behavioral` roda no CI quando há ambiente efêmero disponível. `attestation` é coletada
> uma vez e revalidada periodicamente.

---

## 4. Modelo de pontuação: gates + níveis (não um % único)

**Não usar um score percentual agregado** — convida a gaming e a falso conforto. Em vez disso:

### 4.1 Gates (hard fail)
Checks marcados como `gate` **bloqueiam o deploy** se falharem, salvo exceção registrada
(§5). São o piso de "bom cidadão".

### 4.2 Níveis de maturidade (soft score)
Os checks `score` somam para um **nível**, que mapeia para expectativa operacional:

| Nível    | Significado                                                        |
|----------|--------------------------------------------------------------------|
| Bronze   | Passou em todos os gates. Pode entrar no cluster.                  |
| Prata    | Gates + maioria dos checks de resiliência/observabilidade.        |
| Ouro     | Apto a workloads tier-1 / crítico (PDB, NetworkPolicy, SLO, etc.). |

Cada workload declara o nível **alvo**; o teste reporta nível **atingido** e o gap.
Nível mapeia para expectativa operacional — porcentagem não.

---

## 5. Registro de exceções (a parte mais valiosa)

Quando um check falha mas não pode ser corrigido (legado, terceiro, restrição temporária),
registra-se uma exceção. **O objetivo principal não é o portão — é o catálogo**: durante um
incidente, conseguir responder na hora "esse serviço expõe métricas?".

Requisitos de toda exceção:
- **TTL obrigatório** (`expires_at`) — exceção sem prazo vira dívida permanente.
- **Dono** e **quem concedeu**.
- **Motivo** explícito.
- **Nota de incidente** — o que isso significa quando algo quebra.
- **Controle compensatório** quando houver.

O ledger é **versionado no GitOps** (revisado por PR) e **queryable** pelo `wasp-agent`.

```yaml
# exceptions.yaml — versionado em wasp-gitops, revisado por PR
exceptions:
  - id: EXC-2026-014
    service: legacy-billing-adapter
    check: OBS-001                 # /metrics endpoint
    status: granted                # granted | expired | revoked
    reason: "Serviço de terceiro sem suporte a Prometheus; sem acesso ao código."
    owner: team-payments
    granted_by: silvio
    granted_at: 2026-05-30
    expires_at: 2026-11-30         # obrigatório
    incident_note: >
      Não expõe métricas. Diagnosticar via ALB 5xx/latência e métricas do DynamoDB.
    compensating_control: "Alerta em ALB 5xx + p99 latency."
```

O agente deve expor: `waspctl good-citizen exceptions list/show/expiring` e falhar o gate
quando uma exceção estiver `expired`.

---

## 6. Dimensões e checks

Notação: **Tier** = static/behavioral/attestation · **Classe** = gate/score ·
**Nível** = nível mínimo onde vira obrigatório.

### 3.1 Health & ciclo de vida
| ID      | Check                                                          | Tier        | Classe | Nível  |
|---------|----------------------------------------------------------------|-------------|--------|--------|
| HLT-001 | `readinessProbe` definida                                      | static      | gate   | Bronze |
| HLT-002 | `livenessProbe` definida                                       | static      | gate   | Bronze |
| HLT-003 | readiness e liveness não apontam para o mesmo endpoint         | static      | score  | Prata  |
| HLT-004 | `startupProbe` quando boot é lento                             | static      | score  | Prata  |
| HLT-005 | `terminationGracePeriodSeconds` coerente com o shutdown        | static      | score  | Prata  |
| HLT-006 | App trata `SIGTERM` e drena conexões (graceful shutdown)       | behavioral  | gate   | Prata  |
| HLT-007 | `preStop` quando necessário (deregistration ALB/Istio)         | static      | score  | Ouro   |

### 3.2 Observabilidade
| ID      | Check                                                          | Tier               | Classe | Nível  |
|---------|----------------------------------------------------------------|--------------------|--------|--------|
| OBS-001 | Endpoint `/metrics` responde em formato Prometheus             | behavioral         | gate   | Bronze |
| OBS-002 | `ServiceMonitor`/`PodMonitor` ou annotations de scrape         | static             | gate   | Bronze |
| OBS-003 | Logs estruturados em stdout/stderr (não em arquivo)            | behavioral/attest  | gate   | Bronze |
| OBS-004 | Propagação de trace (W3C traceparent / OTel)                   | behavioral         | score  | Prata  |
| OBS-005 | SLI/SLO declarado para o serviço                               | attestation        | score  | Ouro   |

### 3.3 Recursos & scheduling
| ID      | Check                                                          | Tier        | Classe | Nível  |
|---------|----------------------------------------------------------------|-------------|--------|--------|
| RES-001 | `requests` de CPU e memória setados                            | static      | gate   | Bronze |
| RES-002 | `limits` de memória setados (evita OOM do nó)                  | static      | gate   | Bronze |
| RES-003 | `replicas >= 2` para serviços de tráfego                       | static      | score  | Prata  |
| RES-004 | `PodDisruptionBudget` definido                                 | static      | score  | Ouro   |
| RES-005 | HPA configurado ou justificativa registrada                    | static/attest | score | Prata  |
| RES-006 | `topologySpreadConstraints` / anti-affinity entre réplicas     | static      | score  | Ouro   |

### 3.4 Segurança
| ID      | Check                                                          | Tier          | Classe | Nível  |
|---------|----------------------------------------------------------------|---------------|--------|--------|
| SEC-001 | `runAsNonRoot: true`                                           | static        | gate   | Bronze |
| SEC-002 | `allowPrivilegeEscalation: false`                             | static        | gate   | Bronze |
| SEC-003 | Imagem com tag imutável/digest (não `:latest`)                | static        | gate   | Bronze |
| SEC-004 | Segredos via External Secrets — nada hardcoded                | static        | gate   | Bronze |
| SEC-005 | `readOnlyRootFilesystem: true`                                | static        | score  | Prata  |
| SEC-006 | `capabilities.drop: [ALL]`                                     | static        | score  | Prata  |
| SEC-007 | Imagem de registry aprovado + scan de vulnerabilidade          | static/attest | score  | Prata  |
| SEC-008 | `NetworkPolicy` default-deny + regras explícitas               | static        | score  | Ouro   |

### 3.5 Configuração & 12-factor
| ID      | Check                                                          | Tier          | Classe | Nível  |
|---------|----------------------------------------------------------------|---------------|--------|--------|
| CFG-001 | Config via env/ConfigMap/Secret (não baked na imagem)         | static/attest | gate   | Bronze |
| CFG-002 | Nenhum segredo no manifest ou na imagem                        | static        | gate   | Bronze |
| CFG-003 | Statelessness (sem estado local fora de volume declarado)     | attestation   | score  | Prata  |
| CFG-004 | Disposability — startup rápido                                 | behavioral    | score  | Prata  |

> Nota 12-factor: nem todo princípio é visível no manifest. *Config* e *logs* são
> inferíveis; *disposability* é comportamental; *statelessness* é atestação. Marque o tier
> honestamente — não finja verificar o que não dá.

### 3.6 Dependências & resiliência
| ID      | Check                                                          | Tier          | Classe | Nível  |
|---------|----------------------------------------------------------------|---------------|--------|--------|
| DEP-001 | Dependências declaradas (DynamoDB, Cognito, outros serviços)   | attestation   | score  | Prata  |
| DEP-002 | Timeouts/retries definidos (Istio VirtualService e/ou app)     | static/attest | score  | Prata  |
| DEP-003 | Readiness não fica green se dependência crítica está down      | behavioral    | score  | Ouro   |

### 3.7 Release & rollback
| ID      | Check                                                          | Tier          | Classe | Nível  |
|---------|----------------------------------------------------------------|---------------|--------|--------|
| REL-001 | `ArgoCD Application` com health + sync configurados            | static        | gate   | Bronze |
| REL-002 | Estratégia de rollout definida (RollingUpdate/Argo Rollouts)   | static        | score  | Prata  |
| REL-003 | Caminho de rollback documentado                                | attestation   | gate   | Prata  |

### 3.8 Ownership & documentação
| ID      | Check                                                          | Tier          | Classe | Nível  |
|---------|----------------------------------------------------------------|---------------|--------|--------|
| OWN-001 | Labels de ownership (`app.kubernetes.io/*` + `team`)          | static        | gate   | Bronze |
| OWN-002 | Runbook linkado                                                | attestation   | gate   | Prata  |
| OWN-003 | Contato de on-call definido                                    | attestation   | score  | Prata  |

---

## 7. Estratégia de implementação: wrap, não reimplemente

O tier `static` já é coberto por ferramentas maduras. **Não reescrever linters.** O valor
único do `wasp-agent` é a camada por cima: leveling, ledger de exceções e as regras
org-específicas.

Reaproveitar por baixo:
- **kube-score** / **Polaris (Fairwinds)** — probes, limits, securityContext, PDB.
- **Conftest/OPA** ou **Kyverno** — políticas org-específicas (registry aprovado, External
  Secrets, convenção de `/metrics`, labels).
- **Tier `behavioral`** — namespace efêmero + `curl`/probe scripts próprios (não há
  ferramenta de prateleira boa aqui).

> ⚠️ **Datree está fora.** O projeto open source foi arquivado em jun/2024 e não recebe mais
> manutenção/patches de segurança. Não adotar.

Arquitetura proposta:
```
waspctl good-citizen run ./manifests
        │
        ├── adapters/   → kube-score, polaris, conftest, kyverno (tier static)
        ├── behavioral/ → ephemeral-ns runner (tier behavioral)
        ├── attest/     → coleta/valida atestações
        ├── scoring/    → gates + leveling (Bronze/Prata/Ouro)
        ├── exceptions/ → lê exceptions.yaml do wasp-gitops, valida TTL
        └── report/     → JSON (CI) + tabela (humano) + markdown
```

Integra como **capability do `wasp-agent`** (invocável via Telegram) e como subcomando do
**`waspctl`**.

---

## 8. Saída / formato de relatório

- **JSON** (consumo por CI): por check → `{id, dimension, tier, class, status, level,
  exception_id?}`; mais um resumo `{level_target, level_achieved, gates_failed[], gaps[]}`.
- **Tabela human-readable** para a CLI local.
- **Markdown** anexável ao PR.

Exit codes: `0` = todos os gates ok (com exceções válidas); `1` = gate falhou sem exceção;
`2` = exceção expirada.

---

## 9. Integração CI/CD

1. **Local / pre-commit** — `waspctl good-citizen run` (tier `static`), feedback instantâneo.
2. **PR / CI** — `static` + `behavioral` em namespace efêmero; posta o markdown no PR;
   bloqueia merge se gate falhar.
3. **CD (ArgoCD)** — opcional: admission policy (Kyverno) reforça os gates no cluster como
   última linha — fitness function de atômica → contínua.

---

## 10. Entregáveis e critérios de aceite

O agente deve produzir:
- [ ] Catálogo de checks versionado (`checks/*.yaml`) com `id, dimension, tier, class, level`.
- [ ] Adapters para kube-score + Polaris + Conftest/Kyverno (tier `static`).
- [ ] Runner de namespace efêmero para OBS-001, HLT-006, CFG-004, DEP-003 (tier `behavioral`).
- [ ] Schema + parser do `exceptions.yaml` com validação de TTL.
- [ ] Engine de scoring com gates e níveis Bronze/Prata/Ouro.
- [ ] Saídas JSON + tabela + markdown, com exit codes corretos.
- [ ] Subcomando `waspctl good-citizen` + capability no `wasp-agent`.
- [ ] Doc de uso (local, CI, CD).

Aceite:
- Um serviço sintético "exemplar" atinge **Ouro**.
- Um serviço com `:latest` e sem probes **falha os gates** correspondentes.
- Uma exceção válida **destrava** o gate; uma exceção `expired` **falha** com exit `2`.

---

## 11. Fora de escopo (por enquanto)
- Geração automática de SLOs.
- Painel/dashboard web (o ledger versionado já cobre a query inicial).
- Verificação de custo/FinOps.

---

## 12. Referências
- Google SRE Book — cap. 32, *The Evolving SRE Engagement Model* (Production Readiness Review).
- *Building Evolutionary Architectures* — fitness functions (atômica/holística, disparada/contínua).
- The Twelve-Factor App.
- kube-score, Polaris (Fairwinds), OPA/Conftest, Kyverno.

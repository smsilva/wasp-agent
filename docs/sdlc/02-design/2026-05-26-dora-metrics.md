# DORA Metrics — instrumentação no wasp-agent

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

DORA (DevOps Research and Assessment, hoje parte do Google Cloud) identificou métricas que correlacionam com desempenho de entrega de software e desempenho organizacional. O livro *Accelerate* (Forsgren/Humble/Kim, 2018) é o fundamento estatístico; o relatório anual *State of DevOps* publica benchmarks atualizados.

O `wasp-agent` provisiona plataformas via GitOps (Crossplane Composition + ArgoCD) e expõe telemetria Prometheus em `/telemetry/prometheus`. Existe oportunidade de instrumentar DORA tanto para o **próprio pipeline do wasp-agent** quanto para as **plataformas provisionadas** (meta-observabilidade do que o agente entrega).

## As 4 métricas originais

### 1. Deployment Frequency (DF)
Frequência de deploys em produção.

| Tier | Frequência |
|---|---|
| Elite | Múltiplas vezes por dia |
| High | 1/dia a 1/semana |
| Medium | 1/semana a 1/mês |
| Low | Menos de 1/mês |

Mede *throughput*.

### 2. Lead Time for Changes (LT)
Tempo entre commit e código rodando em produção.

| Tier | Tempo |
|---|---|
| Elite | < 1 hora |
| High | 1 dia a 1 semana |
| Medium | 1 semana a 1 mês |
| Low | > 1 mês |

Latência do pipeline.

### 3. Change Failure Rate (CFR)
% de deploys que causam falha em produção (rollback, hotfix, incidente).

| Tier | % |
|---|---|
| Elite/High | 0-15% |
| Medium | 16-30% |
| Low | > 30% |

Mede *estabilidade*.

### 4. Mean Time to Recovery (MTTR)
Tempo entre detectar falha em produção e restaurar o serviço. Também chamada *Failed Deployment Recovery Time*.

| Tier | Tempo |
|---|---|
| Elite | < 1 hora |
| High | < 1 dia |
| Medium | 1 dia a 1 semana |
| Low | > 1 semana |

Estabilidade.

## 5ª métrica (2021)

### Reliability
Quão bem o serviço atende SLOs (disponibilidade, latência). Menos prescritiva — depende dos targets do produto.

## Por que importam

Dois pares em tensão aparente:

- **Throughput:** DF + LT
- **Stability:** CFR + MTTR

Descoberta-chave: times de alto desempenho **ganham nos dois eixos simultaneamente**. Não há trade-off real entre velocidade e estabilidade.

## Aplicação no wasp-agent

### Camada 1 — pipeline do próprio agente

Dados acessíveis via Git + CI:

- **DF:** contar merges em `main` (proxy de deploy enquanto não houver release automatizado).
- **LT:** `commit_timestamp` → `merge_to_main_timestamp`. Quando houver deploy real, usar `deploy_timestamp`.
- **CFR:** % de PRs que geraram hotfix/revert subsequente. Detectar via commits `revert:` ou `fix:` rotulados.
- **MTTR:** tempo entre abertura de issue/incidente e o commit que o resolve.

### Camada 2 — plataformas provisionadas

O agente provisiona repos GitOps e clusters. Pode coletar DORA *das plataformas que ele cria*:

- ArgoCD expõe `argocd_app_sync_total` e timestamps de sync — alimenta DF e LT.
- Status de sync (`Healthy`/`Degraded`) + watcher do `wasp/watcher.py` — alimenta CFR e MTTR.
- Integrar como métricas Prometheus em `wasp.telemetry` com labels `platform_id`, `chat_id`, `channel`.

## Direção

- Definir mínimo viável: começar pela Camada 1 com script offline lendo `git log`.
- Promover a Draft quando houver decisão sobre escopo (Camada 1 só, ou já incluir Camada 2).
- Comportamento de alerta a decidir: dashboard standalone vs. integração com Telegram (notificar quando CFR sobe).

## Armadilhas a evitar

- **Definir "deploy" mal.** Merge em `main` ≠ produção. Definir claramente o evento.
- **Métrica como OKR individual.** Time gameia (deploys vazios, incidentes não registrados). Usar como diagnóstico do sistema.
- **Otimizar uma métrica isolada.** Aumentar DF reduzindo conteúdo de cada deploy é trapaça se LT subir.
- **Não medir CFR junto com DF.** Deploy rápido sem qualidade é só caos rápido.

## Fora de escopo desta nota

- Implementação concreta (planilha vs. Prometheus vs. ferramenta externa) — decidir em Draft.
- Comparação com benchmarks externos — irrelevante para projeto pessoal; foco em tendência interna.

## Próximo passo

Decidir se faz sentido instrumentar agora (volume de commits do wasp-agent ainda baixo) ou aguardar massa crítica de dados. Possível sinergia com `2026-05-20-token-cost-budget.md` — ambos vivem em `wasp/telemetry`.

## Referências

- *Accelerate* (Forsgren/Humble/Kim, 2018)
- Relatório anual *State of DevOps* (Google Cloud / DORA)
- [dora.dev](https://dora.dev) — definições e ferramenta de auto-avaliação

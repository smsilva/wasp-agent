# Mensageria para watches de CRD

**Date:** 2026-06-03  
**Status:** Idea

## Contexto

O design de `watcher restart resilience` introduz uma tabela `resource_watches` com
coluna `status` (`pending | ready | failed | timeout`). Essa estrutura é funcionalmente
um job queue: o agente produz jobs (watches) e workers os consomem (daemon threads).

À medida que o sistema escala — mais usuários, mais CRDs provisionados em paralelo,
múltiplas instâncias do agente — essa fila SQLite pode se tornar o gargalo.

## Problema latente

Com o design atual:

- Watches são daemon threads dentro do processo do agente. Scaling horizontal implica
  múltiplas instâncias que não compartilham estado de watches.
- SQLite como fila tem limitações de concorrência com writers paralelos.
- Não há backpressure, prioridade, dead-letter queue, nem retry nativo.
- Observabilidade de watches (quantos pendentes, tempo médio de resolução) requer queries
  manuais na tabela.

## Direção exploratória

Substituir (ou complementar) a tabela `resource_watches` por um broker de mensagens
dedicado. Os watches passariam a ser mensagens num topic/stream; workers externos
(ou o próprio agente) os consomem.

### Candidatos

| Broker | Fit | Observações |
|---|---|---|
| **Redis Streams** | Alto | Já comum em stacks Python; `XADD`/`XREADGROUP`; consumer groups para múltiplas instâncias; TTL nativo |
| **RabbitMQ** | Médio | AMQP com DLQ e retry; overhead de infra maior que Redis |
| **Kafka** | Baixo | Excessivo para o volume atual; adequado se watches virarem eventos de auditoria |
| **PostgreSQL LISTEN/NOTIFY** | Médio | Sem nova infra se já usar Postgres; sem durabilidade de mensagens se o consumer cair |

### Mudanças arquiteturais implicadas

1. `WatchRepository.register()` → `broker.publish(kind, name, session_id)` em vez de INSERT
2. Workers (threads ou processos separados) fazem `XREADGROUP` e executam o polling de CRD
3. `resource_watches` SQLite poderia ser mantida como audit log, não como fila primária
4. Recovery no startup desaparece — o broker garante durabilidade nativa

### Quando considerar

- Múltiplas instâncias do agente em produção (Kubernetes Deployment com replicas > 1)
- Volume de watches simultâneos que saturem daemon threads (estimativa: > 50 watches ativos)
- Necessidade de retry automático com backoff para casos de API do cluster indisponível
- Auditoria detalhada de eventos de provisionamento além do que os logs oferecem

## Relação com o design atual

O design de `resource_watches` (02-design/2026-05-16-platform-watcher-restart-resilience.md)
é o passo correto agora: resolve restart resilience com zero dependência nova. A tabela
funciona como fila simples e pode ser mantida como audit log quando/se um broker for
introduzido.

A migração para mensageria não invalida o design atual — é uma evolução natural se o
sistema crescer além de single-instance.
# Persistent audit log — OTel export permanente

**Date:** 2026-05-20  
**Status:** Idea  

## Contexto

OTel está instrumentado (Ciclo 5) e validado contra Jaeger via `make smoke`. Mas o setup atual é dev-only: Jaeger sobe efêmero, spans somem quando o container é destruído. Prometheus mantém séries temporais (métricas), não eventos individuais.

Sem export permanente, "por que o agente provisionou X no dia Y?" não é respondível depois do fato — exatamente o gap de "Governance Debt" / explicabilidade do artigo.

## Problema

- Spans capturam intent (`message_received`, `provision_platform_instance`, `platform_ready`) mas vivem só na sessão do Jaeger local.
- Sem retenção, audit trail real é impossível.
- O autn/authz spec ([[chat-id-allowlist]]) só ganha valor de auditoria se a identidade for vinculada a spans persistidos.

## Direção

- OTLP exporter para um backend persistente. Opções a avaliar:
  - Self-hosted: Tempo + Grafana, Jaeger com storage externo (Elasticsearch/Cassandra).
  - SaaS: Honeycomb, Grafana Cloud, Lightstep.
  - Mínimo viável: exportar OTLP para arquivo JSONL local + rotação.
- Decisão pendente: até onde levar isso sem virar overengineering (projeto é pessoal).
- Política de retenção a definir.

## Fora de escopo desta nota

- Logs estruturados (já existe spec próprio: `2026-05-16-structured-logging.md`).
- Métricas Prometheus de longo prazo — escopo diferente.

## Próximo passo

Promover a Draft junto com o spec de chat_id allowlist — audit log sem identidade é menos útil. Pode consolidar com o spec de structured-logging existente.

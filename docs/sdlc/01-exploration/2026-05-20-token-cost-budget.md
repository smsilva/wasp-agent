# Token/cost budget alerts

**Date:** 2026-05-20  
**Status:** Idea  

## Contexto

Telemetria expõe métricas `agent_*` em `/telemetry/prometheus`. Existe contagem de tokens por turno, mas não há ação automática quando saturação de context window ou pico de tokens acontece.

O artigo de Ari Joury aponta isto como sintoma típico de Operational Debt: time monitora uptime, mas não monitora os indicadores de saúde específicos de LLM (token usage, context saturation).

## Problema

- Sessão longa pode encher o context window do modelo sem aviso, degradando comportamento silenciosamente.
- Loop de retry (futuro, ver `2026-05-20-llm-behavior-evaluation.md`) pode explodir token usage sem teto.
- Sem allowlist ([[chat-id-allowlist]]), um abuso eleva custo de API sem detecção.

## Direção

- Definir SLOs: tokens por turno, tokens por sessão, % do context window usado.
- Threshold alerts via Prometheus / Alertmanager (ou stub equivalente no projeto pessoal).
- Comportamento na saturação a decidir: avisar usuário no Telegram? Forçar reset de sessão? Bloquear `chat_id` temporariamente?

## Fora de escopo desta nota

- Cost optimization (escolha de modelo mais barato, caching de prompt) — outro spec.
- Hard rate limiting — pode ser parte do spec de authz.

## Próximo passo

Promover a Draft quando o allowlist estiver em Draft — faz mais sentido implementar throttling depois que identidade existir.

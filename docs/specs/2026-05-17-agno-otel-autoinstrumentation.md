# Avaliar `openinference-instrumentation-agno` como complemento ao Ciclo 4

**Date:** 2026-05-17  
**Status:** Idea  
**Scope:** Observabilidade do agente — auto-instrumentação OTel via biblioteca oficial agno.

## Problema

O Ciclo 4 (`docs/specs/2026-05-17-opentelemetry-design.md`) adicionou spans e métricas **domain-specific** (`provision_platform_instance`, `agent.watcher.lifecycle`, provisioning counter, watcher duration). Isso cobre a parte de provisionamento e watcher, mas **não captura**:

- Chamadas ao LLM (Bedrock/Claude) — latência, tokens, custo
- Decisões do agente (qual tool foi escolhida, com que argumentos)
- Conversation flow (run id, session id, mensagens)

agno tem suporte first-class a OTel via `openinference-instrumentation-agno` (auto-instrumentação de agentes e tools). A documentação lista backends como Arize Phoenix, Langfuse, Logfire, OpenLIT, etc. Ativando essa instrumentação, ganhamos esses spans **sem código adicional**.

## Decisão a tomar

1. **Adotar `openinference-instrumentation-agno`** — ativa auto-instrumentação. Spans do agente/LLM ficam conectados na mesma trace dos nossos spans de domínio (via OTel context propagation).
2. **Manter como está** — Ciclo 4 cobre o crítico (provisioning + watcher); spans de LLM são luxo enquanto não houver problema observado.

## Pontos a investigar

- Como `openinference-instrumentation-agno` se relaciona com `agno.setup_tracing()` / `tracing=True` no AgentOS. São o mesmo mecanismo ou camadas distintas?
- Quais spans/atributos são emitidos por default? (LLM call, tool call, agent run, run id, session id?)
- Como configurar **um único** OTLP exporter compartilhado entre nossa `telemetry.py` e o auto-instrumentador (sem duplicar TracerProvider).
- Custo em performance — agno tem hot path em produção (telegram webhook → agent → tool).
- Privacidade: o auto-instrumentador captura prompts/respostas do LLM como atributos do span? Se sim, precisa de redacting para Telegram (texto do usuário) e GH_PAT/TELEGRAM_TOKEN não vazarem.

## Saídas esperadas

- Decisão documentada (adotar / não adotar / parcial).
- Se adotar: plano de implementação (`docs/plans/...`) com TDD, integração com `telemetry.py`, configuração de redacting se necessário.

## Referências

- https://docs.agno.com/observability/overview
- https://docs.agno.com/agent-os/tracing/overview
- `docs/specs/2026-05-17-opentelemetry-design.md` (Ciclo 4 — implementado)

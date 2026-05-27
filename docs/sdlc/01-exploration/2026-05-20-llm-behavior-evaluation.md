# LLM behavior evaluation — golden set

**Date:** 2026-05-20  
**Status:** Idea  

## Contexto

A suite de testes atual (cobertura 100%, ruff clean, `make e2e`) valida código determinístico. O comportamento probabilístico do LLM — pedir confirmação antes de chamar a tool, lembrar nome dentro da sessão, recusar quando o usuário declina — só é validado manualmente via smoke test no Telegram.

Isso encaixa no "Evaluation Debt" do artigo de Ari Joury: trocar de modelo (Haiku 4.5 → outro) ou ajustar o system prompt pode regredir comportamento sem que nenhum teste falhe.

## Problema

- Não há golden set de conversas com tool calls esperadas.
- Mudança no system prompt (ex.: a instrução de confirmação adicionada em `1cdca61`) entrou sem teste de regressão automático.
- Custo e latência por turno não são medidos por mudança.

## Direção

- Definir um pequeno conjunto de cenários canônicos:
  - "criar plataforma X" → bot pede confirmação, não chama tool.
  - "criar plataforma X" + "sim" → bot chama `provision_platform_instance` com `name=X`.
  - "criar plataforma X" + "não" → bot não chama tool.
  - Memória de sessão: nome dito → recall na mesma sessão.
- Rodar como step opcional em CI (ou local-only) usando o mesmo modelo via secret.
- Capturar latência e contagem de tokens por cenário; falhar se mudar significativamente.

## Fora de escopo desta nota

- Eval de qualidade textual (BLEU, etc.) — o que importa aqui é tool call correta.
- Comparação multi-modelo — primeiro pin no modelo atual, depois generalizar.

## Próximo passo

Promover a Draft quando decidirmos onde armazenar o golden set (YAML em `tests/eval/`?) e como tornar o custo aceitável no CI.

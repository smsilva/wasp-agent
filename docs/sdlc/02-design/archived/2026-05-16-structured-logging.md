# Structured logging

**Date:** 2026-05-16  
**Status:** Implemented  
**Superseded by:** `docs/superpowers/specs/2026-05-23-logging-design.md`  

Será consolidado com OTel logs no Ciclo 4 (ver [`2026-05-17-opentelemetry-design.md`](./2026-05-17-opentelemetry-design.md)).

## Problema

Os logs atuais vão para stdout em formato texto livre. Não há como ingerir em ferramentas como Loki, CloudWatch Logs Insights ou `jq` sem parsing frágil.

## Proposta

Suporte opcional a logs estruturados em arquivo, ativado via variável de ambiente.

### Configuração

| Variável | Default | Descrição |
|----------|---------|-----------|
| `LOG_FILE` | (vazio) | Path do arquivo de log. Se ausente, mantém comportamento atual (stdout texto). |
| `LOG_LEVEL` | `INFO` | Nível mínimo de log. |

### Formato

JSONL (JSON Lines) — um objeto JSON por linha:

```json
{"timestamp": "2026-05-16T08:30:00Z", "level": "INFO", "message": "Processing message from user 5621932873", "user_id": "5621932873"}
```

Escolha de JSONL: compatível com `jq`, Loki, CloudWatch Logs Insights e a maioria dos ingestores; fácil de parsear linha a linha.

### Comportamento

- Se `LOG_FILE` está definido: escreve JSONL no arquivo E mantém stdout (ou só arquivo — decidir na implementação).
- Criar diretórios intermediários automaticamente (`mkdir -p`).
- Rotação de arquivo fora de escopo nesta spec (delegar ao logrotate ou ao ambiente de deploy).

## Fora de escopo

- Rotação de logs
- Envio direto para serviços externos (Loki push, CloudWatch agent)
- Tracing distribuído

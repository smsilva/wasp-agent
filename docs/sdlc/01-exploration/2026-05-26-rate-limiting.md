# Rate Limiting

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

O allowlist (`wasp/auth.py`) controla *quem* pode usar o agente. Rate limiting controla *quanto* cada usuário pode usar. São camadas ortogonais: um usuário autorizado pode — intencionalmente ou não — flood de mensagens, explodir custo de API Anthropic, ou degradar serviço para outros usuários. Sem rate limiting, o blast radius de um único `chat_id` afeta todo o sistema.

Conecta com `2026-05-20-token-cost-budget.md` (que *alerta* sobre uso excessivo) — rate limiting *bloqueia* antes do alerta ser necessário.

## Dimensões de controle

| Dimensão | O que limita | Exemplo |
|---|---|---|
| Por `chat_id` | Abuso de usuário individual | Max 10 mensagens/minuto por usuário |
| Por canal | Flood via canal específico | Max 100 req/min no webhook Telegram |
| Global | Proteção do sistema inteiro | Max 50 chamadas LLM/minuto no total |
| Por custo | Gasto de API | Max $X de tokens/dia por `chat_id` |

## Algoritmos

**Fixed window:** contador por período (ex: 10 req/min). Simples, mas permite burst no limite da janela (10 req no segundo 59 + 10 req no segundo 61 = 20 req em 2 segundos).

**Sliding window:** suaviza o burst do fixed window. Mais preciso, custo de memória maior.

**Token bucket (recomendado):** bucket com capacidade N; cada req consome 1 token; tokens reabastecidos a taxa R/s. Permite burst legítimo até a capacidade do bucket, throttle suave depois. Intuitivo para configurar.

**Leaky bucket:** garante taxa constante de saída — ideal para proteger sistemas downstream (ex: API Anthropic) de bursts. Complementar ao token bucket.

## Resposta ao cliente

Quando rate limited, o agente deve:

- Responder com mensagem amigável no canal de origem (ex: "Aguarde um momento antes de enviar outra mensagem.") — não retornar HTTP 429 cru ao Telegram.
- **Não revelar** os limites exatos (evita gaming).
- **Não logar como erro** — é comportamento esperado; logar como `INFO` com `chat_id` e `channel`.
- Para flood extremo (ex: bot automatizado): silenciar temporariamente sem notificar.

## Ferramentas

**slowapi** (FastAPI):
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=lambda req: extract_chat_id(req))

@router.post("/webhook")
@limiter.limit("10/minute")
async def webhook(...):
    ...
```

**Redis** (state distribuído — necessário com `uvicorn --workers > 1` ou múltiplos pods):
- `slowapi` suporta backend Redis via `limits` library.
- Sem Redis, limite é por processo — pods diferentes têm contadores independentes.

**In-process** (projeto pessoal, single-process):
- `slowapi` com backend em memória é suficiente para `replicas: 1`.
- Levantar Redis só quando escalar horizontalmente.

## Onde aplicar

```
Telegram → /telegram/webhook → [rate limiter por chat_id] → auth → LLM → tool
```

O rate limiter deve ficar **depois** do parsing do payload (para extrair `chat_id`) e **antes** da chamada LLM.

Para `/telemetry/prometheus`: rate limit por IP, não por `chat_id` — é scrape de infraestrutura.

## Configuração via env vars

```
WASP_RATE_LIMIT_PER_USER=10/minute      # mensagens por usuário
WASP_RATE_LIMIT_GLOBAL_LLM=50/minute    # chamadas LLM totais
WASP_RATE_LIMIT_BURST=5                 # capacidade do token bucket
```

Valores `0` ou ausentes desabilitam o limite — útil para `make e2e` e testes de carga.

## Decisões abertas

1. **Storage:** in-process (simples, suficiente para `replicas: 1`) ou Redis (necessário para HA)?
2. **Granularidade de custo:** limite por mensagens ou por tokens consumidos? Tokens é mais preciso mas requer instrumentação pós-LLM.
3. **Comportamento em burst legítimo:** usuário colando texto longo gera múltiplas mensagens curtas. Janela de 1 minuto vs. 10 minutos muda bastante a experiência.

## Conexão com outros specs

- **Token/cost budget (`2026-05-20-token-cost-budget.md`):** rate limiting é o mecanismo de enforcement; token budget é o monitoramento. Implementar juntos.
- **Auth (`wasp/auth.py`):** rate limiting vem depois de auth — usuário não-autorizado é rejeitado antes de chegar ao limiter.
- **Load testing (`2026-05-26-load-testing.md`):** cenário "webhook flood" do load test valida que o rate limiter funciona sob pressão.
- **Pentest (`2026-05-26-penetration-test.md`):** DoS via flood é vetor explícito — rate limiting é a mitigação.

## Armadilhas

- **Limitar por IP em vez de `chat_id`.** Telegram usa IPs dos servidores deles — todos os usuários teriam o mesmo IP. Sempre usar `chat_id`.
- **Rate limiter antes do parsing.** Se o rate limiter rodar antes de parsear o body, `chat_id` não está disponível. Parsear primeiro, limitar depois.
- **Contar requisições que falham.** Requisições malformadas (400) não devem consumir quota do usuário.
- **Estado em memória com múltiplos workers.** `uvicorn --workers 4` cria 4 processos independentes — cada um tem seu próprio contador. Comportamento incorreto sem Redis.

## Fora de escopo desta nota

- Circuit breaker para APIs downstream (Anthropic, GitHub) — padrão complementar mas spec separado.
- Billing por uso (cobrar usuários por tokens) — requer arquitetura diferente.

## Próximo passo

Promover a Draft junto com `2026-05-20-token-cost-budget.md` — fazem mais sentido implementados na mesma iteração. Ação imediata: adicionar `slowapi` como dependência e testar in-process antes de decidir sobre Redis.

## Referências

- [slowapi](https://github.com/laurentS/slowapi) — rate limiting para FastAPI
- [limits library](https://limits.readthedocs.io/) — backends (memory, Redis, Memcached)
- [Token bucket algorithm](https://en.wikipedia.org/wiki/Token_bucket)
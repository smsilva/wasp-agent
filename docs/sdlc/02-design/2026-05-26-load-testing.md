# Teste de Carga

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

O `wasp-agent` expõe uma API FastAPI com endpoints de webhook (`/telegram/webhook`), telemetria (`/telemetry/prometheus`, `/telemetry/health`) e potencialmente outros canais. O comportamento sob carga é desconhecido: cada requisição pode disparar uma chamada LLM (latência alta, custo variável) e/ou operações GitOps (I/O de rede). Teste de carga responde a perguntas que testes unitários e e2e não respondem: qual é o throughput máximo? Onde está o gargalo? O que quebra primeiro?

## O que testar

### Endpoints

| Endpoint | Característica | Risco |
|---|---|---|
| `POST /telegram/webhook` | Dispara LLM + possível GitOps | Latência alta, custo por requisição |
| `GET /telemetry/prometheus` | Scrape de métricas | Pode travar se geração for lenta |
| `GET /telemetry/health` | Healthcheck | Deve ser sempre < 10ms |

### Cenários

1. **Baseline de latência:** 1 usuário, 1 mensagem por vez — medir p50/p95/p99 sem pressão.
2. **Carga sustentada:** N usuários simultâneos por X minutos — verificar estabilidade de memória e CPU.
3. **Spike:** carga zero → pico abrupto → carga zero — verificar recuperação.
4. **Soak test:** carga moderada por período longo (1h+) — detectar memory leaks, degradação de SQLite, context window saturation.
5. **Webhook flood:** simular flood de mensagens de um único `chat_id` — verificar comportamento do rate limiter (quando existir) e do allowlist.

### O que medir

- Latência: p50, p95, p99, max.
- Throughput: requisições/segundo sustentável.
- Taxa de erro: 4xx/5xx sob carga.
- Consumo de recursos: CPU, memória RSS, file descriptors.
- Comportamento do LLM: tokens por requisição, custo estimado por RPS.
- SQLite: lock contention sob múltiplos workers (se `uvicorn --workers > 1`).

## Ferramentas

### k6 (recomendado para este projeto)

- Scripts em JavaScript/TypeScript, sintaxe declarativa.
- Métricas nativas: latência, throughput, erros — exporta para Prometheus/InfluxDB.
- Modo de execução: local (`k6 run`) ou distribuído (k6 Cloud / k6 Operator no cluster).
- Extensível: `k6-extensions` para WebSocket, gRPC, etc.

```javascript
// scripts/load/webhook.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 10 },   // ramp-up
    { duration: '2m',  target: 10 },   // sustain
    { duration: '30s', target: 0  },   // ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  // 95% < 2s
    http_req_failed:   ['rate<0.01'],   // < 1% erros
  },
};

export default function () {
  const payload = JSON.stringify({
    update_id: Math.floor(Math.random() * 1e9),
    message: {
      message_id: 1,
      from: { id: 123456, is_bot: false, first_name: 'Test' },
      chat: { id: 123456, type: 'private' },
      date: Math.floor(Date.now() / 1000),
      text: '/status',
    },
  });

  const res = http.post('http://localhost:8000/telegram/webhook', payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}
```

### Alternativas

| Ferramenta | Prós | Contras |
|---|---|---|
| **Locust** | Python nativo, fácil de integrar ao projeto | UI menos rica, menos features de threshold |
| **Artillery** | YAML-first, fácil de ler | Menos extensível |
| **wrk / wrk2** | Ultra-leve, bom para baseline de latência | Sem scripting complexo |
| **Gatling** | Relatórios HTML detalhados | Scala/Java, mais pesado |

Locust é segunda opção natural por ser Python — mesma stack do projeto.

## Desafios específicos do wasp-agent

### Custo LLM

Cada requisição ao webhook pode chamar a API Anthropic. Teste de carga com carga real = custo real. Estratégias:

- **Mock do LLM:** `monkeypatch` ou variável de ambiente `WASP_AGENT_MODEL=mock` (se implementado) — testa throughput do FastAPI sem custo.
- **Modelo mais barato:** usar `claude-haiku-*` nos testes de carga, não Opus/Sonnet.
- **Rate limiting próprio:** adicionar `WASP_LOAD_TEST_MODE=true` que responde com fixture sem chamar LLM.

### Autenticação

Webhook do Telegram não tem autenticação HTTP padrão — o agente valida internamente via `is_authorized`. O teste precisa usar `chat_id` autorizado no allowlist ou mockar `is_authorized` como o e2e já faz.

### SQLite sob concorrência

SQLite com `check_same_thread=False` e WAL mode suporta leituras concorrentes, mas escritas serializam. Com `uvicorn --workers > 1`, múltiplos processos competem pelo mesmo arquivo — pode causar `OperationalError: database is locked`. Teste de carga revelaria isso antes de produção.

### Webhook assíncrono

O endpoint do Telegram responde 200 imediatamente e processa em background (`BackgroundTasks`). Latência do endpoint != latência da resposta ao usuário. O teste de carga mede latência do endpoint; a latência end-to-end (até o Telegram receber a resposta) requer instrumentação separada.

## Integração com observabilidade

Com `PROMETHEUS_METRICS_ACTIVE=true` durante o teste:

- `agent_requests_total` — contador de requisições.
- `agent_request_duration_seconds` — histograma de latência.
- Correlacionar com métricas do k6 em Grafana para visão unificada.

Conecta com `2026-05-26-dora-metrics.md`: MTTR pode ser medido pelo tempo que o agente leva para se recuperar após um pico de carga.

## Makefile

```makefile
load-test:
    k6 run scripts/load/webhook.js

load-test-soak:
    k6 run --env DURATION=1h scripts/load/soak.js

load-test-spike:
    k6 run scripts/load/spike.js
```

## Conexão com outros specs

- **DORA Metrics (`2026-05-26-dora-metrics.md`):** MTTR correlaciona com comportamento sob carga; baseline de latência informa SLOs.
- **Token/cost budget (`2026-05-20-token-cost-budget.md`):** teste de carga quantifica custo por RPS — alimenta o budget de tokens.
- **Helm chart (`2026-05-26-helm-chart.md`):** `resources.requests/limits` do chart devem ser baseados em resultados de teste de carga, não em chutes.
- **Observabilidade:** métricas Prometheus coletadas durante o teste são a fonte de verdade para análise de gargalo.

## Armadilhas

- **Testar contra produção.** Nunca rodar teste de carga contra Telegram real ou API Anthropic em produção sem controle de custo explícito.
- **Ignorar o warm-up.** JIT do Python e caches do LLM (se existirem) afetam p99 nas primeiras requisições. Sempre incluir ramp-up.
- **Confundir latência de endpoint com latência percebida.** O agente responde 200 e processa em background — o usuário espera mais do que o k6 mede.
- **SQLite em modo padrão.** Sem WAL mode ativado explicitamente, escrita bloqueia leitura. Verificar antes de qualquer teste concorrente.
- **Um único script de carga.** Cenários diferentes revelam gargalos diferentes. Manter scripts separados por cenário.

## Fora de escopo desta nota

- Teste de performance do modelo LLM em si (latência Anthropic API) — fora de controle do projeto.
- Chaos engineering (falhas de rede, kill de pods) — spec separado se necessário.
- Teste de carga de infraestrutura provisionada (clusters Crossplane) — escopo do GitOps, não do agente.

## Próximo passo

Promover a Draft quando o endpoint `/telegram/webhook` estiver estável e o mock de LLM for implementado. Ação imediata de custo zero: rodar `wrk` ou `k6` contra `/telemetry/health` para ter baseline de latência do servidor sem nenhuma lógica de negócio.

## Referências

- [k6 docs](https://k6.io/docs/)
- [Locust](https://locust.io/)
- [SQLite WAL mode](https://www.sqlite.org/wal.html)
- [FastAPI performance](https://fastapi.tiangolo.com/deployment/concepts/#concurrency-and-parallelism)
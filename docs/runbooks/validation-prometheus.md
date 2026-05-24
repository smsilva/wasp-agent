# Validar Prometheus — independente

Ortogonal aos outros caminhos. Não exige cluster nem Telegram.

```bash
# Standalone
make smoke-prometheus

# Integrado (com o agente rodando)
PROMETHEUS_METRICS_ACTIVE=true make run
curl http://localhost:7777/telemetry/prometheus | grep agent_
```

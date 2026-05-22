#!/usr/bin/env python3
"""
Smoke test: verifica que /telemetry/prometheus expõe métricas OTel do agente.

Pré-requisito: PROMETHEUS_METRICS_ACTIVE deve estar definido (habilita PrometheusMetricReader).

Uso:
    make smoke-prometheus
    # ou: PROMETHEUS_METRICS_ACTIVE=7777 uv run python smoke_prometheus.py

Valida que agent_tool_calls_total e agent_provisioning_total aparecem no output.
"""

import os
import sys

if not os.environ.get("PROMETHEUS_METRICS_ACTIVE"):
    print("ERRO: defina PROMETHEUS_METRICS_ACTIVE (ex: 7777)")
    sys.exit(1)

print(f"PROMETHEUS_METRICS_ACTIVE: {os.environ['PROMETHEUS_METRICS_ACTIVE']}\n")

import wasp.telemetry as telemetry  # noqa: E402 — must come after env check

from prometheus_client import generate_latest  # noqa: E402

EXPECTED = [
    "agent_tool_calls_total",
    "agent_provisioning_total",
    "agent_watcher_polls_total",
    "agent_watcher_duration_seconds",
]


@telemetry.instrument("provision_platform_instance")
def fake_provision():
    return "ok"


@telemetry.instrument("watcher.poll")
def fake_poll():
    return "ok"


print("Chamando funções instrumentadas...")
fake_provision()
fake_poll()

telemetry.provisioning_counter.add(1, {"outcome": "started"})
telemetry.watcher_polls_counter.add(1, {"platform": "test"})
telemetry.watcher_duration.record(1.5, {"platform": "test"})

output = generate_latest(telemetry._prometheus_registry).decode()

print("Verificando métricas...\n")
missing = []
for name in EXPECTED:
    if name in output:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL  {name}")
        missing.append(name)

print()
if missing:
    print(f"FALHOU: métricas ausentes: {missing}")
    sys.exit(1)

print("Todas as métricas presentes.")
print(f"\nOutput ({len(output)} bytes):")
print(output[:800])

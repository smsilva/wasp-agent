#!/usr/bin/env python3
"""
Smoke test: verifica que AgnoInstrumentor gera spans AGENT/LLM/TOOL no Jaeger.

Pré-requisito:
    docker compose up -d   # sobe Jaeger em localhost:4318 (OTLP) e 16686 (UI)

Uso:
    make smoke
    # ou: OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 uv run python smoke_agno_otel.py

Após rodar, abrir http://localhost:16686 e buscar o serviço "wasp-agent".
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
if not endpoint:
    print("ERRO: defina OTEL_EXPORTER_OTLP_ENDPOINT (ex: http://localhost:4318)")
    sys.exit(1)

print(f"OTLP endpoint: {endpoint}")
print(f"Service name:  {os.environ.get('OTEL_SERVICE_NAME', 'wasp-agent')}")
print(f"Hide IO:       {os.environ.get('OTEL_AGNO_HIDE_IO', 'true')}\n")

import wasp.telemetry as telemetry  # noqa: F401,E402 — side-effect: configure() + AgnoInstrumentor

from agno.agent import Agent  # noqa: E402
from agno.models.anthropic import Claude  # noqa: E402

print("AgnoInstrumentor ativo. Criando agent...\n")

agent = Agent(
    model=Claude(id="bedrock/anthropic.claude-4-5-haiku"),
    instructions="Responda em português. Seja conciso.",
    markdown=False,
)

print("Rodando agent (pode levar alguns segundos)...")
response = agent.run("Diga apenas: instrumentação OK")
content = response.content if hasattr(response, "content") else str(response)
print(f"\nResposta: {content}\n")

from opentelemetry import trace  # noqa: E402

trace.get_tracer_provider().force_flush()

print("Spans enviados ao Jaeger.")
print("Abra http://localhost:16686 → Service: wasp-agent → Find Traces")
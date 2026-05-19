.PHONY: run test build smoke smoke-prometheus

run:
	uv run python main.py

test:
	uv run pytest --cov=. --cov-report=term-missing

build:
	uv sync

smoke:
	OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
	OTEL_SERVICE_NAME=wasp-agent \
	OTEL_AGNO_HIDE_IO=false \
	uv run python smoke_agno_otel.py

smoke-prometheus:
	PROMETHEUS_PORT=7777 \
	uv run python smoke_prometheus.py

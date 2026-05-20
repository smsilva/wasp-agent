.PHONY: run test e2e k3d-up k3d-down build smoke smoke-prometheus

K3D_CLUSTER ?= wasp-local

run:
	uv run python main.py

test:
	uv run pytest --cov=. --cov-report=term-missing

e2e:
	uv run pytest tests/e2e/ -m e2e --no-cov -v

k3d-up:
	scripts/k3d-up $(K3D_CLUSTER)

k3d-down:
	scripts/k3d-down $(K3D_CLUSTER)

build:
	uv sync

smoke:
	OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
	OTEL_SERVICE_NAME=wasp-agent \
	OTEL_AGNO_HIDE_IO=false \
	uv run python smoke_agno_otel.py

smoke-prometheus:
	PROMETHEUS_METRICS_ACTIVE=true \
	uv run python smoke_prometheus.py

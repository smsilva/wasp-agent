.PHONY: run test e2e k3d-up k3d-down build lint format smoke smoke-prometheus

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

lint:
	uv run ruff check .

format:
	uv run ruff format .

smoke:
	scripts/smoke

smoke-prometheus:
	PROMETHEUS_METRICS_ACTIVE=true \
	uv run python tests/smoke/smoke_prometheus.py

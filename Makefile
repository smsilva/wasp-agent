.PHONY: run test e2e e2e-with-debug k3d-up k3d-down gitops-up gitops-down build lint format smoke smoke-prometheus local-chat admin-invite admin-revoke admin-list

K3D_CLUSTER ?= wasp-local

run:
	uv run python main.py

test:
	uv run pytest --cov=. --cov-report=term-missing

e2e:
	uv run pytest tests/e2e/ -m e2e --no-cov -v

e2e-with-debug:
	scripts/e2e-with-debug

k3d-up:
	scripts/k3d-up $(K3D_CLUSTER)

k3d-down:
	scripts/k3d-down $(K3D_CLUSTER)

gitops-up:
	scripts/gitops-up

gitops-down:
	scripts/gitops-down

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

local-chat:
	scripts/local-chat-scenario

admin-invite:
	@scripts/admin-invite "$(NAME)" $(CHANNEL)

admin-revoke:
	@scripts/admin-revoke $(CHANNEL) $(ID)

admin-list:
	@scripts/admin-list

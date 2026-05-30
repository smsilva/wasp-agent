.PHONY: run test e2e e2e-with-debug k3d-up k3d-down gitops-up gitops-down build lint format cc smoke smoke-prometheus local-chat admin-bootstrap admin-invite admin-revoke admin-list admin-link postgres-up postgres-down

K3D_CLUSTER ?= wasp-local

run:
	uv run python main.py

# Preserva postgres_data. Para destruir dados: docker compose down postgres -v
postgres-up:
	docker compose up --detach postgres

postgres-down:
	docker compose down postgres

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

cc:
	uv run radon cc wasp/ main.py --show-complexity --average --min B

format:
	uv run ruff format .

smoke:
	scripts/smoke

smoke-prometheus:
	PROMETHEUS_METRICS_ACTIVE=true \
	uv run python tests/smoke/smoke_prometheus.py

local-chat:
	scripts/local-chat-scenario

admin-bootstrap:
	@scripts/admin-bootstrap "$(NAME)" "$(CHANNEL)" "$(ID)"

admin-invite:
	@scripts/admin-invite "$(NAME)" "$(CHANNEL)"

admin-revoke:
	@scripts/admin-revoke "$(CHANNEL)" "$(ID)"

admin-list:
	@scripts/admin-list

admin-link:
	@scripts/admin-link "$(USER_ID)" "$(CHANNEL)" "$(ID)"

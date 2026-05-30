# docker-compose Postgres Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar Postgres como serviço de infra local no docker-compose, com volume persistente, targets no Makefile e runbook.

**Architecture:** `docker-compose.yml` único com dois serviços (postgres + jaeger). App roda fora do compose via `make run`. Credenciais via `.env`. Named volume `postgres_data` persiste entre restarts; destruído apenas com `docker compose down -v`.

**Tech Stack:** Docker Compose v2, PostgreSQL 17 Alpine.

---

### Task 1: Atualizar `docker-compose.yml`

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Substituir o conteúdo de `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"
      - "4318:4318"
    environment:
      COLLECTOR_OTLP_ENABLED: "true"

volumes:
  postgres_data:
```

- [ ] **Step 2: Verificar sintaxe**

```bash
docker compose config --quiet
```

Esperado: sem output (sintaxe válida).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(infra): add postgres service with persistent volume to docker-compose"
```

---

### Task 2: Atualizar `.env.example`

**Files:**
- Modify: `.env.example`

O arquivo já tem `# DATABASE_URL=` na linha 57. O objetivo é:
1. Atualizar essa linha com o exemplo concreto apontando para o compose.
2. Adicionar o bloco `POSTGRES_*` antes da linha `DATABASE_BACKEND`.

- [ ] **Step 1: Localizar o bloco DATABASE no `.env.example`**

```bash
grep -n "DATABASE\|POSTGRES" .env.example
```

Esperado: linhas ao redor de 48-57 com comentários `DATABASE_BACKEND`, `DATABASE_FILE`, `DATABASE_URL`.

- [ ] **Step 2: Substituir o bloco DATABASE existente**

Localizar o bloco (linhas ~47-57):

```
# Backend de persistência (auth + sessões agno).
# Valores: 'sqlite' (default), 'postgres' (ainda não implementado — ver
# docs/sdlc/02-design/2026-05-30-postgres-readiness.md).
# DATABASE_BACKEND=sqlite

# Path do arquivo SQLite — ignorado se DATABASE_BACKEND != sqlite.
# DATABASE_FILE=agent.db

# DSN do Postgres — ignorado se DATABASE_BACKEND=sqlite.
# Exemplo: postgresql://user:pass@localhost:5432/wasp_agent
# DATABASE_URL=
```

Substituir por:

```
# Backend de persistência (auth + sessões agno).
# Valores: 'sqlite' (default), 'postgres'.
# DATABASE_BACKEND=sqlite

# Path do arquivo SQLite — ignorado se DATABASE_BACKEND != sqlite.
# DATABASE_FILE=agent.db

# DSN do Postgres — ignorado se DATABASE_BACKEND=sqlite.
# DATABASE_URL=postgresql://wasp:wasp@localhost:5432/wasp_agent

# Postgres (docker-compose) — usar com DATABASE_BACKEND=postgres
# POSTGRES_USER=wasp
# POSTGRES_PASSWORD=wasp
# POSTGRES_DB=wasp_agent
```

- [ ] **Step 3: Verificar resultado**

```bash
grep -n "DATABASE\|POSTGRES" .env.example
```

Esperado: `DATABASE_BACKEND`, `DATABASE_FILE`, `DATABASE_URL` com exemplo concreto, e bloco `POSTGRES_*`.

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "docs(env): add POSTGRES_* vars and concrete DATABASE_URL example"
```

---

### Task 3: Atualizar `.env` local

**Files:**
- Modify: `.env` (não commitado — gitignored)

- [ ] **Step 1: Adicionar o bloco Postgres ao `.env` local**

Adicionar ao final do arquivo `.env` (ou abaixo do bloco `DATABASE_*` existente):

```bash
# Postgres (docker-compose) — usar com DATABASE_BACKEND=postgres
# POSTGRES_USER=wasp
# POSTGRES_PASSWORD=wasp
# POSTGRES_DB=wasp_agent
# DATABASE_URL=postgresql://wasp:wasp@localhost:5432/wasp_agent
```

Descomente as linhas se quiser usar Postgres localmente.

- [ ] **Step 2: Confirmar que `.env` não está staged**

```bash
git status .env
```

Esperado: `.env` não aparece (gitignored).

---

### Task 4: Atualizar `Makefile`

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Atualizar linha `.PHONY`**

Linha atual:
```
.PHONY: run test e2e e2e-with-debug k3d-up k3d-down gitops-up gitops-down build lint format cc smoke smoke-prometheus local-chat admin-bootstrap admin-invite admin-revoke admin-list admin-link
```

Nova linha:
```
.PHONY: run test e2e e2e-with-debug k3d-up k3d-down gitops-up gitops-down build lint format cc smoke smoke-prometheus local-chat admin-bootstrap admin-invite admin-revoke admin-list admin-link postgres-up postgres-down
```

- [ ] **Step 2: Adicionar targets `postgres-up` e `postgres-down`**

Adicionar após o target `run:` (linha 5):

```makefile
# Preserva postgres_data. Para destruir dados: docker compose down postgres -v
postgres-up:
	docker compose up --detach postgres

postgres-down:
	docker compose down postgres
```

**Atenção:** a indentação dos comandos deve ser TAB, não espaços. O Makefile falha silenciosamente com espaços.

- [ ] **Step 3: Verificar sintaxe**

```bash
make --dry-run postgres-up
```

Esperado: `docker compose up --detach postgres`

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "feat(make): add postgres-up and postgres-down targets"
```

---

### Task 5: Criar `docs/runbooks/local-infra.md`

**Files:**
- Create: `docs/runbooks/local-infra.md`

- [ ] **Step 1: Criar o arquivo**

```markdown
# Infra local (docker compose)

## Postgres

```bash
make postgres-up   # sobe Postgres em background (porta 5432)
make postgres-down # derruba; dados em postgres_data sobrevivem
```

Para destruir os dados: `docker compose down postgres -v`

DATABASE_URL de desenvolvimento: `postgresql://wasp:wasp@localhost:5432/wasp_agent`

## Jaeger

```bash
docker compose up --detach jaeger   # UI em http://localhost:16686
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/local-infra.md
git commit -m "docs(runbooks): add local-infra runbook for postgres and jaeger"
```

---

### Task 6: Validação end-to-end

- [ ] **Step 1: Garantir que `.env` tem as vars descomentadas**

```bash
grep -E "^POSTGRES_|^DATABASE_URL=" .env
```

Esperado:
```
POSTGRES_USER=wasp
POSTGRES_PASSWORD=wasp
POSTGRES_DB=wasp_agent
DATABASE_URL=postgresql://wasp:wasp@localhost:5432/wasp_agent
```

- [ ] **Step 2: Subir Postgres**

```bash
make postgres-up
```

Esperado: container `wasp-agent-postgres-1` em estado `running`.

- [ ] **Step 3: Verificar healthcheck**

```bash
docker compose ps
```

Esperado: coluna `STATUS` mostra `healthy` para o serviço `postgres` (pode levar ~10s).

- [ ] **Step 4: Conectar ao banco**

```bash
docker compose exec postgres psql --username=wasp --dbname=wasp_agent --command="\l"
```

Esperado: lista de databases incluindo `wasp_agent`.

- [ ] **Step 5: Testar auth com Postgres**

```bash
DATABASE_BACKEND=postgres \
DATABASE_URL=postgresql://wasp:wasp@localhost:5432/wasp_agent \
uv run python -c "
from wasp.auth import get_repository
r = get_repository()
print(type(r).__name__)
"
```

Esperado: `PostgresAuthRepository`

- [ ] **Step 6: Derrubar e confirmar volume persiste**

```bash
make postgres-down
docker volume ls | grep postgres_data
```

Esperado: volume `wasp-agent_postgres_data` listado.

- [ ] **Step 7: Subir novamente e confirmar dados persistem**

```bash
make postgres-up
docker compose exec postgres psql --username=wasp --dbname=wasp_agent --command="\l"
```

Esperado: banco `wasp_agent` ainda presente.

- [ ] **Step 8: Limpar**

```bash
make postgres-down
```

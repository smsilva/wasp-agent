# Dockerfile / docker-compose com Postgres

**Status:** Implemented  
**Data:** 2026-05-30  
**Motivação:** Adicionar Postgres como serviço de infra local no compose; remover assunção implícita de SQLite como único backend; definir volumes persistentes. Checklist de production-readiness §6 (linhas 124-127).

---

## Escopo

**In-scope:**

- Adicionar serviço `postgres` ao `docker-compose.yml` existente (ao lado do Jaeger).
- Named volume `postgres_data` para persistência entre restarts.
- Credenciais lidas do `.env` via variáveis `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.
- Atualizar `.env.example` (e `.env`) com bloco Postgres comentado + `DATABASE_URL` de exemplo.
- Targets `make postgres-up` / `make postgres-down` no Makefile.
- Novo runbook `docs/runbooks/local-infra.md`.

**Out-of-scope:**

- Hardening do Dockerfile (usuário não-root, `.dockerignore`, alpine/distroless) — ver `2026-05-30-dockerfile-hardening.md`.
- App container no compose — app roda localmente via `make run`.
- Renomeação de prefixo `WASP_AGENT_*` — spec separado.

---

## Decisões

- **Banco único** (`wasp_agent`) — auth e sessions agno compartilham a mesma instância/database via `DATABASE_URL`.
- **Compose de infra only** — apenas Postgres e Jaeger; app roda fora do compose em dev.
- **Um único `docker-compose.yml`** — profiles e overrides adicionam complexidade desnecessária para dois serviços.
- **`POSTGRES_DB`** (não `POSTGRES_DATABASE`) — mantém paridade com a convenção da imagem oficial.
- **`postgres:17-alpine`** — versão estável e menor que `latest`.

---

## 1. `docker-compose.yml`

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

`healthcheck` com `pg_isready` permite `depends_on: condition: service_healthy` se o app entrar no compose futuramente.

---

## 2. `.env` e `.env.example`

Adicionar ao final (valores comentados como defaults sugeridos):

```bash
# Postgres (docker-compose) — usar com DATABASE_BACKEND=postgres
# POSTGRES_USER=wasp
# POSTGRES_PASSWORD=wasp
# POSTGRES_DB=wasp_agent
# DATABASE_URL=postgresql://wasp:wasp@localhost:5432/wasp_agent
```

`DATABASE_URL` já existe comentada no `.env.example`; atualizar/consolidar com o exemplo concreto.

---

## 3. Makefile

```makefile
# Preserva postgres_data. Para destruir dados: docker compose down postgres -v
postgres-up:
	docker compose up --detach postgres

postgres-down:
	docker compose down postgres
```

Adicionar `postgres-up postgres-down` à linha `.PHONY`.

---

## 4. `docs/runbooks/local-infra.md`

Novo runbook para serviços de infra local:

```markdown
# Infra local (docker compose)

## Postgres

make postgres-up   # sobe Postgres em background (porta 5432)
make postgres-down # derruba; dados em postgres_data sobrevivem

Para destruir os dados: docker compose down postgres -v

DATABASE_URL de desenvolvimento: postgresql://wasp:wasp@localhost:5432/wasp_agent

## Jaeger

docker compose up -d jaeger   # UI em http://localhost:16686
```

---

## 5. Arquivos alterados

| Arquivo | Mudança |
|---|---|
| `docker-compose.yml` | adiciona serviço `postgres` + volume `postgres_data` |
| `.env.example` | adiciona bloco `POSTGRES_*` + `DATABASE_URL` com exemplo concreto |
| `.env` | espelha bloco comentado do `.env.example` |
| `Makefile` | targets `postgres-up`, `postgres-down`; atualiza `.PHONY` |
| `docs/runbooks/local-infra.md` | novo runbook |

---

## 6. Validação

```bash
docker compose up -d postgres
docker compose ps          # postgres healthy
psql postgresql://wasp:wasp@localhost:5432/wasp_agent -c "\l"

DATABASE_BACKEND=postgres \
DATABASE_URL=postgresql://wasp:wasp@localhost:5432/wasp_agent \
uv run python -c "from wasp.auth import get_repository; print(get_repository())"

make postgres-down
```

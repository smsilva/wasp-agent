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

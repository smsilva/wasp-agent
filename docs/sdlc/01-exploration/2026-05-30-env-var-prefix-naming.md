# Repensar prefixo de env vars do projeto

**Status:** Idea
**Data:** 2026-05-30
**Motivação:** o prefixo atual `WASP_AGENT_` é redundante (o projeto se chama wasp-agent; o sufixo `_AGENT_` não distingue nada). Surgiu durante o brainstorming da preparação para PostgreSQL, onde precisaríamos congelar nomes como `WASP_AGENT_DB_BACKEND`, `WASP_AGENT_DB_FILE`, `WASP_AGENT_DB_URL`.

---

## 1. Estado atual

Env vars conhecidas com o prefixo `WASP_AGENT_`:

| Variável | Onde |
|---|---|
| `WASP_AGENT_NOTIFIER` | `wasp/clients/__init__.py` (override de canal) |
| `WASP_AGENT_DB_BACKEND` | `wasp/auth/__init__.py` |
| `WASP_AGENT_DB_FILE` | `wasp/auth/_connection.py` |
| `WASP_AGENT_INVITE_TTL_HOURS` | `wasp/auth/sqlite_repository.py` |

Documentadas em:
- `CLAUDE.md` (seção "Env vars")
- `docs/runbooks/auth-admin.md`
- `.env.example` (se existir — verificar)

## 2. Opções a considerar (não decididas)

- `WASP_*` — curto, claro, sem redundância.
- `WAGENT_*` — preserva contexto de "agent" sem repetir "wasp".
- Manter `WASP_AGENT_*` — zero churn, mas perpetua redundância.
- Outro padrão. (AGENT_*, WASP_AUTH_*, etc — mas cuidado para não criar confusão futura se o projeto crescer e precisar de mais categorias de env vars.)

## 3. Decisão pendente

A renomeação não é urgente nem bloqueante. Ficará para um spec dedicado quando houver decisão sobre o nome novo. Até lá, novos env vars adicionados ao projeto continuam usando `WASP_AGENT_` para coerência.

Próximas vars que entrariam: `WASP_AGENT_DB_URL` (DSN do Postgres, ainda a ser implementado — ver spec da preparação para PostgreSQL).

## 4. Quando retomar

Quando qualquer destes acontecer:
- Decisão sobre o nome novo do prefixo.
- Migração efetiva para PostgreSQL (boa janela para renomear junto, evitando dois churns).
- Crescimento da lista de env vars (>10) tornando o prefixo ruidoso em scripts/Helm/docker-compose.
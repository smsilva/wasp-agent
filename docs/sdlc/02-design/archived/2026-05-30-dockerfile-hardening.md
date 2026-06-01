# Dockerfile hardening

**Status:** Implemented  
**Data:** 2026-05-30  
**Motivação:** Atender checklist de production-readiness (linha 124-127 de `docs/references/production-readiness-checklist.md`). Imagem atual usa `python:3.14-slim`, roda como root, sem `.dockerignore`.

---

## Escopo

- Trocar `python:3.14-slim` por imagem menor (alpine ou distroless).
- Adicionar usuário não-root (`RUN adduser --disabled-password appuser`).
- Criar `.dockerignore` excluindo `.env`, `__pycache__`, `tests/`, `*.db`, `logs/`.
- Avaliar `readOnlyRootFilesystem` (exige mover `agent.db` e `logs/` para volume).
- Imagem versionada por tag imutável (sem `latest` em produção).

## Fora do escopo

- Helm chart / Kubernetes security context — spec separado (`2026-05-26-helm-chart.md`).

## Dependências

Implementar após `2026-05-30-dockerfile-compose.md` (que define como o app é containerizado e quais volumes existem).

---

## Avaliação: readOnlyRootFilesystem

- **SQLite backend:** escreve `agent.db` em `/app`; requer volume ou `emptyDir` montado em `/app`. Incompatível com `readOnlyRootFilesystem: true` sem adaptação.
- **Postgres backend:** nenhuma escrita em disco pela aplicação (sessions e auth no banco). Compatível com `readOnlyRootFilesystem: true`.
- **Logs:** verificar se `configure_logging()` abre arquivo; se sim, mover para stdout.
- **Recomendação:** habilitar no Helm chart (spec `2026-05-26-helm-chart.md`) condicionado a `DATABASE_BACKEND=postgres`. SQLite + readOnly exige volume explícito — documentar como opt-in.

## Notas de implementação

- Base image trocada para `python:3.14-alpine` (imagem menor, sem glibc desnecessário).
- `adduser -D appuser` (sintaxe alpine) + `chown -R appuser:appuser /app` + `USER appuser`.
- `.dockerignore` criado excluindo `.env`, `tests/`, `*.db`, `logs/`, `docs/`, `.git`, caches.
- uv e python base ainda usam tags flutuantes (`latest` / `3.14-alpine`); pin para digest imutável recomendado em CI/CD na etapa de build da imagem final.

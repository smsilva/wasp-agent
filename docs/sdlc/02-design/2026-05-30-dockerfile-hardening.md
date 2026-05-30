# Dockerfile hardening

**Status:** Draft  
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

# Validation paths

Quatro formas de validar o `wasp-agent`. Cada uma valida coisas diferentes — escolha conforme o que você mudou.

| Caminho | Quando usar | Arquivo |
|---|---|---|
| **A. E2E automatizado** | Após qualquer mudança de código | [`validation-e2e.md`](validation-e2e.md) |
| **B. Smoke test Telegram** | Canal Telegram, auth, comportamento do LLM | [`validation-telegram.md`](validation-telegram.md) |
| **C. Prometheus** | Métricas e instrumentação | [`validation-prometheus.md`](validation-prometheus.md) |
| **D. Local chat** | Iteração rápida sem Telegram | [`validation-local-chat.md`](validation-local-chat.md) |
| **E. Ciclo GitOps completo** | Mudanças em `provision.py`, `watcher.py` ou Composition | [`validation-gitops.md`](validation-gitops.md) |

`make e2e` e `make e2e-with-debug` são obrigatórios antes de declarar qualquer feature pronta (ver `CLAUDE.md §16`).

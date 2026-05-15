---
id: SEC-001
severity: Medium
status: resolved
opened: 2026-05-13
resolved: 2026-05-15
---

# SEC-001: `.env.example` não documenta `TELEGRAM_WEBHOOK_SECRET_TOKEN`

## Descrição

O arquivo `.env.example` omite `TELEGRAM_WEBHOOK_SECRET_TOKEN`, que é necessária para autenticar requisições de webhook do Telegram na biblioteca agno.

## Impacto

Um deploy baseado no `.env.example` não terá a variável configurada. Em modo produção, uma requisição do Telegram com o header `X-Telegram-Bot-Api-Secret-Token` causa `ValueError` → HTTP 500 — o bot não aceita mensagens sem autenticação silenciosamente, mas falha de forma opaca e difícil de diagnosticar.

## Fix

Adicionar ao `.env.example`:

```
TELEGRAM_WEBHOOK_SECRET_TOKEN=your-webhook-secret-token
```

Gerar com:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Resolução

Adicionado ao `.env.example` com instrução de geração.
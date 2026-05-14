---
id: SEC-003
severity: Low
status: open
opened: 2026-05-13
---

# SEC-003: `APP_ENV=development` desabilita autenticação do webhook

## Descrição

A biblioteca agno desabilita completamente a validação do `TELEGRAM_WEBHOOK_SECRET_TOKEN` quando `APP_ENV=development`. Esse comportamento não está documentado em `.env.example` nem em nenhum arquivo do projeto.

## Código relevante (agno)

```python
# agno/os/interfaces/telegram/security.py
def _is_dev_mode() -> bool:
    return os.getenv("APP_ENV", "").lower() == "development"

def validate_webhook_secret_token(secret_token_header):
    if _is_dev_mode():
        log_warning("Bypassing secret token validation in development mode")
        return True  # aceita qualquer requisição
    ...
```

## Impacto

Se `APP_ENV=development` for definido acidentalmente em produção (template de CI/CD, variável global), qualquer origem pode enviar mensagens ao bot sem autenticação.

## Fix

Documentar no `.env.example` com aviso explícito:

```
# WARNING: APP_ENV=development disables webhook authentication entirely
# APP_ENV=development
```

Garantir que pipelines de produção não definam `APP_ENV=development`.
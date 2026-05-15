# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

## Current Progress

**Ciclos 1 e 2 completos — mergeados para `main`.**

### Ciclo 1 (completo)
- `main.py` — Agent + Telegram interface + SQLite storage (agno 2.6.5 API)
- `tests/conftest.py` + `tests/test_main.py` — 3 testes, 100% cobertura
- Smoke test validado: bot respondeu no Telegram, memória de sessão funcionando

### Ciclo 2 (completo)
- `tools/provision.py` — modelos Pydantic (`PlatformManifest`, `PlatformSpec`, `RegionSpec`, `ServiceSpec`) + `provision_platform_instance` tool com `@tool(requires_confirmation=True)`
- `tools/__init__.py` — re-exporta `provision_platform_instance`
- `tests/test_provision.py` — 4 testes, 100% cobertura
- `tests/conftest.py` — mock `agno.tools` + teardown de `tools`/`tools.provision`
- `main.py` — tool registrado em `Agent(tools=[provision_platform_instance])`
- 7 testes, 100% cobertura
- `GH_PAT` fine-grained criado no GitHub para `smsilva/wasp-gitops` (Contents: write, expira Jun 14, 2026) e adicionado ao `.env`

**Decisões do ciclo 2:**
- Commit direto em branch `dev` do `smsilva/wasp-gitops` (não PR)
- Path: `infrastructure/tenants/{name}.yaml`
- Pydantic models para gerar o manifesto (não Jinja2)
- PAT fine-grained no MVP (não GitHub App)
- Default domain: `wasp.silvios.me`, default region: `us-east-1`
- `yaml.safe_dump()` para serialização segura
- `DEFAULT_REGIONS` como tupla, `None` default na assinatura da função

## What Worked

- `agno[anthropic,os,telegram]` como extra único cobre todas as deps runtime
- `Telegram(agent=agent, token=token)` — agent passado no construtor da interface
- Mock de `dotenv.load_dotenv` no conftest evita que `.env` real interfira nos testes
- ngrok + `setWebhook` com `secret_token` para desenvolvimento local
- `TELEGRAM_WEBHOOK_SECRET_TOKEN` gerado com `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `yaml.safe_dump()` previne injeção de objetos Python arbitrários em manifests GitOps
- PAT fine-grained com escopo mínimo: apenas `smsilva/wasp-gitops`, apenas Contents write

## What Didn't Work

- Declarar `anthropic`, `fastapi`, `uvicorn` como deps individuais — agno não os encontra; usar extras
- `Telegram(token=token)` sem `agent=` — lança `ValueError` em runtime
- `monkeypatch.setattr("dotenv.main.load_dotenv", ...)` — não afeta a referência exportada; usar `dotenv.load_dotenv`
- `SqliteAgentStorage` / `add_history_to_messages` — não existem no agno 2.6.5; usar `SqliteDb` / `add_history_to_context`
- `DEFAULT_REGIONS = ["us-east-1"]` como default de função — lista mutável é Python gotcha; usar tupla + `None`
- `yaml.dump()` com input de usuário — usa Dumper completo; sempre `yaml.safe_dump()` para manifests

## Next Steps

### Ciclo 2 — smoke test
1. **Rodar o bot localmente** (ver `docs/runbooks/telegram-local-dev.md`) e enviar mensagem de provisionamento via Telegram. Verificar que o commit aparece em `smsilva/wasp-gitops` branch `dev`. O `GH_PAT` já está no `.env`.

### Ciclo 3
2. **Watcher assíncrono:** `asyncio.create_task` in-process + notificação proativa no Telegram quando `Platform` atingir `Ready: True`.

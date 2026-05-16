# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

## Current Progress

**Ciclos 1 e 2 completos — mergeados para `main`. Smoke test do ciclo 2 validado.**

### Ciclo 1 (completo)
- `main.py` — Agent + Telegram interface + SQLite storage (agno 2.6.5 API)
- `tests/conftest.py` + `tests/test_main.py` — 3 testes, 100% cobertura
- Smoke test validado: bot respondeu no Telegram, memória de sessão funcionando

### Ciclo 2 (completo + smoke test validado)
- `tools/provision.py` — modelos Pydantic + `provision_platform_instance` tool
- `tools/__init__.py` — re-exporta `provision_platform_instance`
- `tests/test_provision.py` — 4 testes, 100% cobertura
- `main.py` — tool registrada, system prompt refinado (tom, escopo, confirmação)
- 7 testes, 100% cobertura
- Commit real confirmado em `smsilva/wasp-gitops` branch `dev`

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
- Confirmação via LLM (system prompt) funciona bem no Telegram
- Tool retornando dict genérico com apenas `status` e `message` — LLM não vaza detalhes internos
- WatchFiles recarrega o agent automaticamente ao salvar arquivos durante dev

## What Didn't Work

- Declarar `anthropic`, `fastapi`, `uvicorn` como deps individuais — agno não os encontra; usar extras
- `Telegram(token=token)` sem `agent=` — lança `ValueError` em runtime
- `monkeypatch.setattr("dotenv.main.load_dotenv", ...)` — não afeta a referência exportada; usar `dotenv.load_dotenv`
- `SqliteAgentStorage` / `add_history_to_messages` — não existem no agno 2.6.5; usar `SqliteDb` / `add_history_to_context`
- `DEFAULT_REGIONS = ["us-east-1"]` como default de função — lista mutável é Python gotcha; usar tupla + `None`
- `yaml.dump()` com input de usuário — usa Dumper completo; sempre `yaml.safe_dump()` para manifests
- `@tool(requires_confirmation=True)` com Telegram — o agno emite `RunPausedEvent` mas a interface Telegram não tem handler para ele; a tool é silenciosamente rejeitada. Usar confirmação via LLM no system prompt
- Retornar campos técnicos no dict da tool (`commit_sha`, `file_path`) — o LLM os surfacia todos ao usuário; incluir só `status` e `message`

## Next Steps

### Ciclo 3
1. **Watcher assíncrono:** `asyncio.create_task` in-process que observa o status do `Platform` CRD e envia notificação proativa no Telegram quando `Ready: True`.

### Backlog
2. **Logging estruturado:** suporte opcional a JSONL em arquivo via `LOG_FILE` env var. Ver `docs/specs/2026-05-16-structured-logging.md`.
# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

## Current Progress

**Ciclo 1 completo e validado.** Branch `dev` pronto para merge/PR.

**Ciclo 2 — design aprovado, implementação pendente.**

### Ciclo 1 (completo)
- `main.py` — Agent + Telegram interface + SQLite storage (agno 2.6.5 API)
- `tests/conftest.py` + `tests/test_main.py` — 3 testes, 100% cobertura
- Smoke test validado: bot respondeu no Telegram, memória de sessão funcionando

### Ciclo 2 — design (esta sessão)
- Brainstorm `docs/brainstorms/agno-crossplane-provisioning-flow.md` analisado e todas as decisões resolvidas
- Spec aprovado e commitado: `docs/specs/2026-05-15-platform-provisioning-design.md`
- `CLAUDE.md` atualizado com `§11. Platform provisioning`

**Decisões tomadas no ciclo 2:**
- Commit direto em branch `dev` do `smsilva/wasp-gitops` (não PR)
- Path: `infrastructure/tenants/{name}.yaml`
- Pydantic models para gerar o manifesto (não Jinja2)
- `asyncio.create_task` in-process para watcher (deferred para ciclo 3)
- PAT fine-grained no MVP (não GitHub App)
- Default domain: `wasp.silvios.me`, default region: `us-east-1`

## What Worked

- `agno[anthropic,os,telegram]` como extra único cobre todas as deps runtime
- `Telegram(agent=agent, token=token)` — agent passado no construtor da interface
- Mock de `dotenv.load_dotenv` no conftest evita que `.env` real interfira nos testes
- ngrok + `setWebhook` com `secret_token` para desenvolvimento local
- `TELEGRAM_WEBHOOK_SECRET_TOKEN` gerado com `python3 -c "import secrets; print(secrets.token_hex(32))"`

## What Didn't Work

- Declarar `anthropic`, `fastapi`, `uvicorn` como deps individuais — agno não os encontra; usar extras
- `Telegram(token=token)` sem `agent=` — lança `ValueError` em runtime
- `monkeypatch.setattr("dotenv.main.load_dotenv", ...)` — não afeta a referência exportada; usar `dotenv.load_dotenv`
- `SqliteAgentStorage` / `add_history_to_messages` — não existem no agno 2.6.5; usar `SqliteDb` / `add_history_to_context`

## Next Steps

### Imediato
1. Escolher destino do branch `dev`: merge local para `main` ou abrir PR.

### Ciclo 2 — implementação
2. Criar plano de implementação a partir do spec:
   `docs/specs/2026-05-15-platform-provisioning-design.md`
   - Fluxo: invocar `superpowers:writing-plans` com o spec como entrada
   - Arquivos a criar: `tools/__init__.py`, `tools/provision.py`, `tests/test_provision.py`
   - Adicionar deps: `PyGithub>=2.0.0`, `pyyaml>=6.0`
   - Registrar `provision_platform_instance` nas tools do agent em `main.py`

### Ciclo 3
3. Watcher assíncrono: `asyncio.create_task` in-process + notificação proativa no Telegram quando `Platform` atingir `Ready: True`.

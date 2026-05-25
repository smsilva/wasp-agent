# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão, autenticação multi-canal por invite, e suporte futuro a Discord/Slack.

Ciclos 1–6 estão em `main`. Ciclo 7 (autenticação multi-canal) + logging estruturado estão em `dev`.

## Current Progress

**Sessão 2026-05-23 (parte 3) — Validação Telegram completa + documentação**

- Fix: `webhook_with_auth` em `_install_start_token_handler` retornava 422 em todo POST do Telegram. Causa: ausência de type annotations `request: Request` e `background_tasks: BackgroundTasks` — FastAPI tentava resolver como query params. Fix: importar `Request` (`starlette.requests`) e `BackgroundTasks` (`starlette.background`) dentro de `get_router_with_auth` e anotar os parâmetros. Registrado em §12a do `CLAUDE.md`.
- Regression test adicionado em `tests/test_main.py::test_webhook_with_auth_has_fastapi_type_annotations` — verifica via `inspect.signature` que as anotações estão presentes. Testes que chamam o endpoint diretamente não capturam esse bug.
- Fluxo GitOps completo executado e validado: ngrok + webhook + auth bootstrap (`make admin-bootstrap`) + `make gitops-up` + confirmação no Telegram → commit em `smsilva/wasp-gitops` branch `dev` → ArgoCD sync → Crossplane reconcile → notificação `Ready` no Telegram (~2 min do ciclo confirmação→Ready).
- Apêndice de `validation.md` expandido de 3 bullets para seção E.1–E.7 com pré-requisitos, sequência de comandos, verificações por etapa, tempo de ciclo observado e limpeza (`make gitops-down`).
- `telegram-local-dev.md` Step 6 renomeado para "Verificar setup (chat básico)" com nota explícita que mensagens conversacionais não exigem auth e que o fluxo completo (incluindo `provision_platform_instance`) continua em `validation.md §B`.

**Sessão 2026-05-23 (parte 2) — Auth multi-canal (Ciclo 7) + fixes de validação**

- Plan `docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md` executado fim-a-fim (9 tasks TDD): `wasp/auth.py` (schema `auth_users` / `auth_identities` / `auth_invites`, API `init_db`/`is_authorized`/`create_user`/`link_identity`/`create_invite`/`redeem_invite`/`revoke_identity`/`list_identities`/`has_any_user`/`bootstrap_admin`), guard em `provision_platform_instance` (deny silencioso + canal `local` confiável), handler `/start <token>` no webhook do Telegram (com validação do `X-Telegram-Bot-Api-Secret-Token`), CLI admin (`scripts/admin-{invite,revoke,list,bootstrap}` + Make targets), métrica `wasp_auth_denied_total{channel,reason}`, `auth.init_db()` no startup, runbook `docs/runbooks/auth-admin.md`.
- Bug encontrado **só** via `make e2e-with-debug`: `_install_start_token_handler` buscava route com `path == "/webhook"`, mas o `APIRouter` do agno usa `prefix="/telegram"`. Fix: `endswith("/webhook")`. Lição em §12a do `CLAUDE.md`.
- Smoke test do Telegram detalhado em `docs/runbooks/validation.md` §B.

**Sessão 2026-05-23 (parte 1) — Logging:** subsistema completo (`wasp/logging.py`, `JSONFormatter`, `chat_id_var` ContextVar, 22 testes, cobertura 100%).

**Sessão 2026-05-21:** smoke Telegram manual validado; validação GitOps end-to-end rodada; `fix(gitops)` na ordem do `scripts/gitops-up`.

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md` | Implemented |
| `docs/sdlc/02-design/2026-05-20-local-chat.md` | Implemented |
| `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` | Idea — opção A (OAuth direto GitHub/Google) |
| `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` | Idea — opção B (Cognito como hub federado) |
| `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` | Idea |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |

### Plans ativos

Nenhum em execução.

### Open Security Issues

Nenhuma issue ativa em `docs/security/issues/`.

## What Worked

- **Smoke test completo até Ready (~2 min):** fluxo Telegram → commit `smsilva/wasp-gitops` → ArgoCD sync → Crossplane reconcile → notificação funcionou sem intervenção manual além da confirmação no Telegram.
- **Subagent-driven development para documentação:** brainstorming → spec → plano → execução com subagentes por task manteve o fluxo organizado e produziu documentação auto-suficiente.
- **`inspect.signature` para regression tests de type annotations:** testes diretos no endpoint não capturam ausência de anotações FastAPI; `inspect.signature` é o gate correto e corre em microsegundos.
- **`telegram-local-dev.md` como guia de setup apenas:** separar "setup de túnel + webhook" de "smoke test completo" evita que o leitor pule a etapa de auth bootstrap.

## What Didn't Work

- **Testes unitários diretos no `webhook_with_auth`** passaram sem as type annotations porque chamam o endpoint como função Python, bypassando FastAPI. O bug só apareceu ao usar o Telegram real. Solução: `inspect.signature` no teste + smoke test manual.
- **Auth bootstrap esquecido no guia inicial:** minha primeira síntese do `telegram-local-dev.md` ignorou as etapas B.2–B.4 de `validation.md`, levando ao "Acesso negado" ao confirmar o provisionamento. Corrigido com nota explícita no Step 6 do runbook.

## Next Steps

### 1. Security review (CLAUDE.md §9, §9a)

Auth multi-canal está em `dev` mas não passou por security review. Cobrir:

- **Race em `redeem_invite`** (`wasp/auth.py:173–183`): envolver em `BEGIN IMMEDIATE`.
- **Telemetria de token inválido**: incrementar `wasp_auth_denied_total{reason="invalid_token"}` em `_process_start_token`.
- **`bootstrap_admin` deixa `auth_users` órfão** se `link_identity` lança `IntegrityError`.
- **Invites sem `channel`/`channel_id` permitem first-claimer wins**: documentar como limitação conhecida.
- **`os.chmod(agent.db, 0o600)` após `init_db()`**.
- **`init_db()` chamado em todo `is_authorized`**: gate por flag módulo-nível.
- **Fluxo `/start <token>`**: revisar entropy, exposição em logs, headers.

### 2. Decidir entre opção A (CLI device flow OAuth) e opção B (Cognito federation)

Specs `Idea` em `docs/sdlc/02-design/`. Promover uma para Draft e criar plano.

### 3. Definir prioridade dos demais specs em `Idea`

- `2026-05-20-llm-behavior-evaluation.md` — golden set para detectar regressões no system prompt.
- `2026-05-20-token-cost-budget.md` — alertas de orçamento de tokens.

## Backlog

- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`.
- **Reduzir `MAX_COMPLEXITY` para 10** — refatorar `provision_platform_instance` (`wasp/provision.py`, CC=15) e atualizar limite em `tests/test_complexity.py`.

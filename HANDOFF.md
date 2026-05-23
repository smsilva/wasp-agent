# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão, autenticação multi-canal por invite, e suporte futuro a Discord/Slack.

Ciclos 1–6 estão em `main`. Ciclo 7 (autenticação multi-canal) + logging estruturado estão em `dev`.

## Current Progress

**Sessão 2026-05-23 (parte 2) — Auth multi-canal (Ciclo 7) + fixes de validação**

- Plan `docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md` executado fim-a-fim (9 tasks TDD): `wasp/auth.py` (schema `auth_users` / `auth_identities` / `auth_invites`, API `init_db`/`is_authorized`/`create_user`/`link_identity`/`create_invite`/`redeem_invite`/`revoke_identity`/`list_identities`/`has_any_user`/`bootstrap_admin`), guard em `provision_platform_instance` (deny silencioso + canal `local` confiável), handler `/start <token>` no webhook do Telegram (com validação do `X-Telegram-Bot-Api-Secret-Token`), CLI admin (`scripts/admin-{invite,revoke,list,bootstrap}` + Make targets), métrica `wasp_auth_denied_total{channel,reason}`, `auth.init_db()` no startup, runbook `docs/runbooks/auth-admin.md`.
- Final review do auth-multichannel rodou após Task 9 — APPROVED_WITH_CONCERNS. Achados não-bloqueantes ficaram registrados no Backlog abaixo.
- Bug encontrado **só** via `make e2e-with-debug` (não via `make test`): `_install_start_token_handler` buscava route com `path == "/webhook"`, mas o `APIRouter` do agno usa `prefix="/telegram"`. Fix: `endswith("/webhook")`. Lição entrou como **§12a do `CLAUDE.md`** e como diretiva obrigatória em §16 (rodar `make test` + `make e2e-with-debug` ao fim de todo ciclo).
- E2E `agent_client` fixture passou a monkeypatchar `wasp.auth.is_authorized` — sem isso o auth guard nega o `session_id="tg:..."` e o teste falha mascarado em 404 do Gitea (registrado em §19 do `CLAUDE.md`).
- Smoke test do Telegram agora detalhado em `docs/runbooks/validation.md` §B com: setup ngrok, descobrir `user.id`, dois fluxos de auth (bootstrap vs invite/deep link), roteiro de mensagens, verificação opcional do auth deny path, reset de estado.
- `make local-chat` validado em runtime: roteiro 5/5 OK (greet → memória → confirmação → tool chamada), canal `local` confirmado como `TRUSTED_CHANNELS` (auth bypassada).

**Sessão 2026-05-23 (parte 1) — Logging:** subsistema completo (`wasp/logging.py`, `JSONFormatter`, `chat_id_var` ContextVar, rotação diária + 50 MB, 22 testes, cobertura 100%). Já estava em `dev` no início da sessão.

**Sessão 2026-05-21:** smoke Telegram manual validado; validação GitOps end-to-end rodada; `fix(gitops)` na ordem do `scripts/gitops-up`; spec local-chat arquivado.

### Specs ativos

| Arquivo | Status |
|---|---|
| `docs/sdlc/02-design/2026-05-20-chat-id-allowlist.md` | Implemented |
| `docs/sdlc/02-design/2026-05-20-local-chat.md` | Implemented |
| `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md` | Idea — opção A (OAuth direto GitHub/Google), concorre com cognito-federation |
| `docs/sdlc/02-design/2026-05-21-auth-cognito-federation.md` | Idea — opção B (Cognito como hub federado), alinha com `aws-saas-platform` |
| `docs/sdlc/02-design/2026-05-20-llm-behavior-evaluation.md` | Idea |
| `docs/sdlc/02-design/2026-05-20-token-cost-budget.md` | Idea |
| `docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md` | Deferred |

### Plans ativos

Nenhum em execução. `docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md` está completo.

### Open Security Issues

Nenhuma issue ativa em `docs/security/issues/` (só `archived/`).

## What Worked

- **TDD via subagent driven development (skill `subagent-driven-development`)**: implementer + spec reviewer + code quality reviewer por task. 9 tasks executadas em sequência sem retrabalho, com final review holístico capturando achados não-bloqueantes.
- **Subagents com modelo Sonnet** para tasks mecânicas (Task 8, wire-up trivial) e Opus para revisão final — escolha de modelo proporcional à complexidade conserva tempo e custo.
- **`make e2e-with-debug` como gate obrigatório**: bug do `/telegram/webhook` prefix só apareceu lá. `make test` sozinho passou contra `MagicMock(path="/webhook")` realista demais para o mock, mas incorreto contra o agno real.
- **Webhook secret-token enforcement antes do parse**: `webhook_with_auth` valida o `X-Telegram-Bot-Api-Secret-Token` no topo, antes de chamar `_process_start_token`. Sem isso, atacantes que conhecem a URL do ngrok poderiam consumir invites.
- **Idempotent Prometheus Counter registration**: `_PROM_REGISTRY._names_to_collectors` check evita `Duplicated timeseries` quando `sys.modules.pop` reimporta `wasp.telemetry` entre testes.
- **Stub explícito de `is_authorized` no E2E fixture**: alinhado ao padrão existente do `_select_notifier`. Documenta o gap entre "rodar a feature" e "exercitar o auth real".
- **Documentar o smoke test completo (auth + Telegram) em `validation.md` §B**: dois fluxos de auth (bootstrap vs invite), passos numerados, mensagens de erro esperadas, verificação opcional do deny path com métrica Prometheus.

## What Didn't Work

- **Unit tests com `MagicMock(path="/webhook")`**: passavam contra implementação quebrada porque mock não tinha o prefixo do `APIRouter`. Solução: adicionar pelo menos um teste com path prefixado (`"/telegram/webhook"`) para qualquer wrapper de router agno.
- **Suposição que cobertura 100% + ruff clean = pronto**: cobertura mede linhas exercitadas, não comportamento real. O bug do prefixo tinha 100% de linhas cobertas pelos mocks. Validação E2E é o gate funcional.
- **Final review como passo final do skill**: revelou 4 IMPORTANTs (race em `redeem_invite`, telemetria de token inválido, IntegrityError em `bootstrap_admin`, first-claimer wins em invites sem channel). Nenhum é blocker mas todos são scope-creep relativo ao plano. Decisão: backlog estruturado, sem reabrir o ciclo.
- **Spec compliance review sem verificar comportamento integrado**: Task 3 passou no spec review com `path == "/webhook"` porque o spec não dizia nada sobre o prefixo. Compliance ≠ funcional.

## Next Steps

### 1. Security review (CLAUDE.md §9, §9a)

Auth multi-canal está em `dev` mas não passou por security review. Cobrir:

- **Race em `redeem_invite`** (`wasp/auth.py:173–183`): read+write em statements separados sob `with con:`. Envolver em `BEGIN IMMEDIATE` para serializar webhook concorrentes com o mesmo token.
- **Telemetria de token inválido**: incrementar `wasp_auth_denied_total{reason="invalid_token"}` quando `redeem_invite` retorna `None` em `_process_start_token`.
- **`bootstrap_admin` deixa `auth_users` órfão** se `link_identity` lança `IntegrityError`: transação única ou rollback explícito.
- **Invites sem `channel`/`channel_id` permitem first-claimer wins**: documentar em "Limitações conhecidas" do `docs/runbooks/auth-admin.md`.
- **`os.chmod(agent.db, 0o600)` após `init_db()`**: hardenar deploys onde o arquivo existe antes do `os.umask`.
- **`init_db()` chamado em todo `is_authorized`**: gate por flag módulo-nível para reduzir conexões na hot path.
- **Validação do webhook + auth path**: revisar end-to-end o fluxo `/start <token>` (entropy do token, exposição em logs, headers).

### 2. Decidir entre opção A (CLI device flow OAuth) e opção B (Cognito federation)

Specs `Idea` em `docs/sdlc/02-design/`. Gatilho: existência da CLI `wasp` concreta + escolha entre standalone (A) vs AWS-bound (B). Promover uma para Draft e criar plano.

### 3. Definir prioridade dos demais specs em `Idea`

- `2026-05-20-llm-behavior-evaluation.md` — golden set para detectar regressões no system prompt.
- `2026-05-20-token-cost-budget.md` — alertas de orçamento de tokens.

Ambos podem virar Approved + plano quando houver capacidade.

## Backlog

- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`, Deferred) — persistir `platform_watches` em SQLite.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`.

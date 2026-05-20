# Authn/Authz — chat_id allowlist

**Date:** 2026-05-20  
**Status:** Idea  
**Prioridade:** Alta — precede os demais specs abertos em 2026-05-20.

## Contexto

Hoje qualquer `chat_id` do Telegram que conheça o handle do bot pode interagir, invocar `provision_platform_instance` e provisionar tenants no `wasp-gitops`. Não há identidade nem autorização — só a confirmação manual no LLM (system prompt). Vazamento do token do bot = acesso irrestrito.

CLAUDE.md §9 já lista isto como próximo passo de segurança; este spec formaliza.

## Problema

- Sem allowlist, qualquer `chat_id` autenticado pelo Telegram passa pelo agente.
- Sem registro de identidade na trilha de audit (spans), não é possível atribuir uma ação a um usuário humano específico além do `chat_id` cru.
- Security review (CLAUDE.md §9) está bloqueado até existir um modelo de autorização para revisar.

## Direção

- Allowlist declarativa por variável de ambiente ou arquivo (`ALLOWED_CHAT_IDS` ou similar).
- Verificação no entrypoint do webhook Telegram, antes de o agno processar a mensagem.
- Negação silenciosa ou explícita (a decidir no draft) com log estruturado.
- Decisão pendente: estática (env var) vs. dinâmica (SQLite, gerenciada por um chat admin).

## Fora de escopo desta nota

- Multi-tenancy real (mapear `chat_id` → namespace/permissões granulares).
- Integração com IdP externo (Keycloak, Auth0).
- Rate limiting por usuário — spec separado se necessário.

## Próximo passo

Promover a Draft quando decidirmos entre allowlist estática (env) ou dinâmica (SQLite + comando admin).

# Auth via Cognito (federation hub) — opção B

**Date:** 2026-05-21  
**Status:** Idea  
**Prioridade:** Média — alternativa arquitetural ao spec `2026-05-21-cli-device-flow-oauth.md`. Captura a direção discutida em 2026-05-21 para não se perder. Decidir entre as duas opções antes de promover qualquer uma a Draft.  
**Concorre com:** `2026-05-21-cli-device-flow-oauth.md` (opção A — OAuth direto com GitHub/Google implementado em wasp-agent).

## Contexto

O spec MVP (`2026-05-20-chat-id-allowlist.md`, Approved) resolve auth para Telegram via invite + `/start <token>`. Para canais sem identidade nativa (CLI, web futura, integrações server-to-server), precisamos de auth real.

A opção A (`cli-device-flow-oauth`) propõe implementar OAuth direto com GitHub + Google em wasp-agent: rotas `/cli/auth/*`, tabela `auth_tokens`, página HTML de seleção de provedor, troca de code, Bearer token próprio.

Este spec propõe uma **alternativa arquitetural**: delegar federação de identidade ao **Amazon Cognito**, alinhado com o padrão já adotado em [`/home/silvios/git/aws-saas-platform`](file:///home/silvios/git/aws-saas-platform/docs/architecture/auth-multitenant.md).

## Princípio

> **Cognito federa qualquer IdP upstream e entrega um JWT normalizado. wasp-agent valida o JWT via JWKS e mapeia o `sub` Cognito a um `user_id` interno.**

Cognito é hub de federação — Google, Microsoft, Okta, Auth0, Keycloak, ou nativo Cognito (email/senha) — e wasp-agent vê uma única credencial: o JWT Cognito.

## Direção (esboço, não desenho final)

### Componentes

- **Cognito User Pool dedicado** (`wasp-agent-users`) — ou reuso do User Pool do aws-saas-platform (decisão pendente, §"Pré-requisitos").
- **Cognito App Client** para a CLI wasp-agent — flow `authorization_code` com PKCE.
- **Cognito Hosted UI** em `auth.wasp.silvios.me` (ou subdomínio próprio) — serve login + seleção de provedor.
- **JWKS endpoint** público do Cognito — wasp-agent baixa as chaves para validar JWT.

### Flow `wasp login`

1. `wasp login` (binário CLI futuro) levanta servidor HTTP local em porta efêmera.
2. Abre browser em:
   ```
   https://auth.wasp.silvios.me/oauth2/authorize
     ?client_id=<app-client-id>
     &response_type=code
     &scope=openid+email+profile
     &redirect_uri=http://localhost:<local-port>/cb
     &code_challenge=<pkce>
     &code_challenge_method=S256
   ```
3. Cognito Hosted UI mostra a tela de login com os provedores configurados (Google, Microsoft, etc., ou login nativo Cognito).
4. Após autenticação no provedor upstream, Cognito troca o code por tokens internamente, e redireciona para `http://localhost:<local-port>/cb?code=<code>`.
5. CLI troca o `code` por `id_token` + `access_token` + `refresh_token` via POST `/oauth2/token` direto ao Cognito (com PKCE verifier).
6. CLI persiste os tokens em `~/.config/wasp/credentials` (chmod 600). `id_token` é o JWT que vai como Bearer.
7. Comandos subsequentes mandam `Authorization: Bearer <id_token>`.
8. wasp-agent valida o JWT contra a JWKS do Cognito (cache local), extrai `sub`, resolve em `auth_identities` para o `user_id` interno.

### Mudanças no servidor wasp-agent

- **Middleware FastAPI/Starlette** que valida JWT no header `Authorization` contra a JWKS do Cognito (lib: `python-jose` ou `authlib`). Injeta `user_id` resolvido no `run_context`.
- **Nada de rotas OAuth, página HTML, troca de code, ou tabela de tokens.** Todo o flow de login é Cognito.
- Tabela `auth_identities` estendida: `channel="cognito"`, `channel_id=<cognito-sub>` (UUID estável que sobrevive a re-login).

### Comando admin para pré-vincular usuário

Mantém o padrão do MVP: admin pré-vincula um Cognito sub a um `user_id` antes do primeiro login. Sem auto-signup.

```
make admin-invite NAME="Alice" CHANNEL=cognito ID=<cognito-sub>
```

Como o admin descobre o `sub` antes do primeiro login? Duas opções:

- **(a)** Admin cria o user manualmente no User Pool via console AWS, copia o `sub`, gera o invite.
- **(b)** Token de invite genérico (sem channel pré-vinculado, como no MVP) — primeiro login OAuth consome o invite e cria a identity automaticamente. Mais ergonômico, mas precisa de uma página intermediária para o usuário colar o token após autenticar.

Decisão pendente (§"Pré-requisitos").

## Comparação com opção A (OAuth direto GitHub/Google)

| Dimensão | Opção A — OAuth direto | Opção B — Cognito |
|---|---|---|
| Provedores suportados no MVP | GitHub + Google (hard-coded) | Qualquer OIDC + nativo Cognito (config no console) |
| Adicionar Microsoft/Okta/Keycloak | spec + código + tabela | clicar no console AWS |
| Código em wasp-agent | rotas OAuth + página HTML + tabela `auth_tokens` + flow de Bearer | middleware de validação JWT (10-20 linhas) |
| UI de login | precisamos servir (HTML simples) | Cognito Hosted UI (customizável, gratuita) |
| Tabela `auth_tokens` | necessária (Bearer próprio) | dispensada (JWT é credencial completa) |
| Refresh token | precisa implementar | Cognito gerencia |
| MFA | depende do provedor (GitHub/Google) | Cognito faz nativo (TOTP, SMS) |
| Setup AWS | nenhum | User Pool + App Client + domínio + DNS |
| Custo | grátis | grátis até 50k MAU/mês (free tier permanente) |
| Local dev sem internet | OAuth funciona contra GitHub/Google | precisa do User Pool de dev acessível, ou auth disabled |
| Consistência arquitetural | wasp-agent diverge do aws-saas-platform | mesma arquitetura, mesmo mental model |
| Risco de lock-in AWS | nenhum | médio — depende do Cognito; migração para Auth0/Keycloak é refactor |
| GitHub como provedor | nativo | só via OIDC adapter (GitHub não é OIDC-compliant 100%) — pode ser deal-breaker se GitHub for prioridade |

## Por que considerar Cognito

- **Padrão já estabelecido em projeto irmão** (`aws-saas-platform`). Mesma equipe, mesmo stack — replicar o mental model reduz curva de aprendizado e bug surface.
- **Federação livre**: usuário corporativo com Okta entra sem wasp-agent precisar saber o que é Okta. Cognito faz a tradução.
- **Drasticamente menos código próprio**: middleware JWT é uma fração do trabalho de implementar OAuth do zero, validar state/CSRF, gerenciar refresh, etc.
- **MFA grátis**: Cognito suporta TOTP/SMS nativamente. Opção A herda MFA do provedor (que pode ou não estar ativado pelo user).
- **Onboarding consistente**: a mesma página de login (Hosted UI) que aws-saas-platform usa.

## Por que NÃO Cognito (argumentos a favor da opção A)

- **GitHub é prioridade alta**: Cognito não tem federação nativa para GitHub. Workaround via OIDC parcial existe ([reference](https://aws.amazon.com/blogs/security/how-to-use-github-as-an-identity-provider-for-aws-iam-identity-center/)), mas é fragil.
- **Self-hosted/air-gapped**: se wasp-agent vai rodar em ambientes sem AWS (on-prem cluster, lab pessoal), Cognito não é opção. Opção A funciona contra qualquer endpoint OAuth público.
- **Lock-in AWS**: já comprado para o aws-saas-platform; questionável para wasp-agent se ele puder rodar standalone.
- **Latência adicional**: cada request precisa validar JWT contra JWKS — overhead pequeno mas existente. Mitigável com cache local da JWKS.
- **Complexidade de setup inicial**: mexer em User Pool, App Client, domínio customizado, DNS — atrito real antes do primeiro `wasp login`.

## Modelo de dados (estende o MVP)

Mesma extensão do `auth_identities` do spec MVP:

```sql
INSERT INTO auth_identities (channel, channel_id, user_id, linked_at)
VALUES ('cognito', '<cognito-sub-uuid>', '<wasp-user-id>', '<iso-ts>');
```

**Não precisa** de tabela `auth_tokens` — JWT do Cognito tem `exp` próprio, validação contra JWKS confirma autenticidade, revogação acontece no Cognito (sign-out / desativar user).

Span attributes (já no MVP) refletem o `user.id` resolvido. Adicionar opcionalmente `auth.cognito_sub` para audit cruzado com logs do Cognito.

## Configuração (esboço)

```
WASP_AGENT_AUTH_MODE=cognito          # cognito | disabled (default)
WASP_AGENT_COGNITO_USER_POOL_ID=us-east-1_XXXXX
WASP_AGENT_COGNITO_APP_CLIENT_ID=xxxxx
WASP_AGENT_COGNITO_REGION=us-east-1
WASP_AGENT_COGNITO_DOMAIN=auth.wasp.silvios.me
```

JWKS URI é derivada: `https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/jwks.json`. wasp-agent baixa no startup e cacheia.

## Fora de escopo deste spec

- **`wasp` CLI binário** em si — assume sua existência (mesma premissa da opção A).
- **Multi-tenancy real** (tenant_id no JWT, Pre-Token Lambda, Istio policies). O wasp-agent é single-tenant por enquanto. Quando virar multi-tenant, replicar o padrão do `aws-saas-platform/docs/architecture/auth-multitenant.md`.
- **Self-signup via Cognito Hosted UI**: usuário cria conta sozinho. Decisão futura — por ora, manter o gate de invite admin.
- **Refresh token rotation**: Cognito suporta, deixar para iteração.
- **Sign-out global** (revogação de todas sessões): Cognito suporta via `AdminGlobalSignOut`. Adicionar quando necessário.

## Pré-requisitos para promover a Draft

1. **Decisão entre as duas opções** (este spec vs. `cli-device-flow-oauth.md`). Pesar:
   - Importância do GitHub como provedor (Cognito é fraco aí).
   - Aceitação do lock-in AWS.
   - Viabilidade de rodar wasp-agent sem AWS em dev/lab.
2. **Escopo do User Pool**: dedicado ao wasp-agent ou reuso do User Pool do aws-saas-platform? Reuso evita duplicação mas mistura users.
3. **Provedor inicial**: Cognito nativo (email/senha), Google federado, ou ambos? Marcar como ponto de entrada e expandir.
4. **Estratégia de invite**: admin descobre `sub` antes (opção a) ou token genérico + página intermediária (opção b)?
5. **wasp CLI binário**: bash wrapper, Python (`click`/`typer`), ou Go? Influencia complexidade do PKCE local server.
6. **Dev sem AWS**: `WASP_AGENT_AUTH_MODE=disabled` + `TRUSTED_CHANNELS={"local"}` (já no MVP) cobrem dev local. Suficiente?

## Relação com o spec MVP

Este spec **estende** `2026-05-20-chat-id-allowlist.md` sem conflito:

- Reusa `auth_users` e `auth_identities` (PK composta `(channel, channel_id)` já suporta `channel="cognito"`).
- **Não** adiciona `auth_tokens` (diferente da opção A).
- Reusa o `agent.db`.
- Span `user.id` (MVP) passa a refletir o user real resolvido via JWT em vez de `"local-operator"` placeholder.

Telegram (canal `tg`) **continua nativo** — não passa por Cognito. JWT só para CLI/web.

## Decisões fechadas até aqui (conversa de 2026-05-21)

- **Cognito é alternativa viável e arquiteturalmente alinhada com `aws-saas-platform`.**
- **Híbrido: Telegram nativo + Cognito para o resto.** Não migrar Telegram para Cognito (não faz sentido — Telegram já entrega identidade).
- **Sem `auth_tokens` tabela**: JWT Cognito é a credencial.
- **Sem auto-signup**: continua dependendo de invite admin (alinhado com o MVP).
- **Não decidido**: GitHub como provedor (Cognito é fraco). Pode ser deal-breaker para a opção B.

## Próximo passo

Manter ambas as opções (A e B) como `Idea`. Decidir entre elas quando:

- A CLI `wasp` virar artefato concreto (gatilho comum às duas).
- Houver clareza sobre o público alvo (devs only → favorece A com GitHub; público misto → favorece B com Cognito).
- Houver decisão sobre dependência de AWS para o wasp-agent (favorece A se quer standalone, B se já é AWS-bound).
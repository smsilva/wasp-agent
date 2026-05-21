# CLI device flow + OAuth direto (Nível 3 — opção A)

**Date:** 2026-05-21  
**Status:** Idea  
**Prioridade:** Média — não bloqueia o MVP de auth multi-canal (`2026-05-20-chat-id-allowlist.md`), mas é o caminho natural para evoluir do `local-chat` "trusted host" para uma CLI real autenticada.  
**Concorre com:** `2026-05-21-auth-cognito-federation.md` (opção B — Cognito como hub federado). Decidir entre os dois antes de promover qualquer um a Draft.

## Contexto

O spec `2026-05-20-chat-id-allowlist.md` (Approved, em execução) cobre Telegram via `(channel, channel_id) → user_id` com invite admin + `/start <token>`. Funciona porque o Telegram entrega identidade verificável.

O canal `local` (curl / `scripts/local-chat`) **não tem identidade verificável** — qualquer cliente HTTP escolhe o `session_id` que quiser. Decisão atual: tratar `local` como "trusted host" (network boundary, sem allowlist) e expor o endpoint AgentOS só em `127.0.0.1` em produção. Ver `2026-05-20-chat-id-allowlist.md` §11 e o plano de execução Task 2.

Esse hack funciona para dev e E2E mas não escala para:

- Operador rodando uma CLI no laptop contra um wasp-agent remoto.
- Pipelines CI invocando o agent.
- Integrações server-to-server (script Slack/PagerDuty disparando provisioning).

Este spec captura a direção da próxima iteração — formalizar agora para não perder contexto antes de virar prioridade.

## Problema

Como dar identidade verificável a clientes que não chegam por um canal de mensageria (Telegram, Slack, Discord)?

- Sem identidade: a única defesa é network isolation. Impede uso legítimo remoto.
- Com identidade fraca (token estático no `.env`): risco operacional alto, sem rotação, sem audit por humano.
- Com identidade forte: OAuth delegando ao IdP do operador (GitHub para devs, Google para usuários gerais).

## Direção (esboço, não desenho final)

Padrão estilo `gh auth login` / `gcloud auth login` / `flyctl auth login`:

1. `wasp login` (binário CLI futuro, ainda não existe) levanta um servidor HTTP local em porta efêmera.
2. Abre browser em `https://<wasp>/cli/auth?state=<csrf>&port=<local-port>` (URL do servidor wasp-agent).
3. Servidor wasp-agent serve uma página com botões "Continuar com GitHub" / "Continuar com Google" e dispara o OAuth correspondente.
4. Após callback do provedor, servidor wasp-agent resolve a identidade (`github.login` ou `google.email`), procura em `auth_identities` (recusa se não pré-vinculado — ver §"Fora de escopo"), gera um Bearer token e persiste em `auth_tokens`.
5. Servidor wasp-agent redireciona o browser para `http://localhost:<local-port>/cb?token=<bearer>`.
6. CLI captura o token, persiste em `~/.config/wasp/credentials` (chmod 600), fecha o servidor local.
7. Comandos subsequentes (`wasp provision ...`, `wasp status ...`) mandam `Authorization: Bearer <token>` no header.

Mudanças no servidor wasp-agent:

- Rota `/cli/auth/start` (página HTML com botões "Continuar com GitHub" / "Continuar com Google").
- Rota `/cli/auth/callback/github` e `/cli/auth/callback/google` (recebem code do provedor, trocam por user, geram Bearer, redirecionam pro localhost do CLI).
- Middleware Bearer auth no AgentOS endpoint (`/agents/.../runs`) — quando presente, resolve `user_id` via `auth_tokens` e injeta no `run_context`.
- Tabela nova `auth_tokens (token PK, user_id FK, created_via_channel, created_at, last_used_at, revoked_at)` para audit + revogação. `created_via_channel` é `github` ou `google` — útil para audit ("token X foi emitido via login GitHub do user Y").

Como isso unifica os canais:

| Canal | Como identidade chega | Linhas em `auth_identities` |
|---|---|---|
| `tg` | Telegram entrega `user.id` | `(tg, <user.id>, user_id)` |
| `github` | OAuth GitHub durante `wasp login` | `(github, <github-login>, user_id)` |
| `google` | OAuth Google durante `wasp login` | `(google, <google-email>, user_id)` |
| `slack`/`discord` futuros | Canal entrega `member_id` | `(slack, <member_id>, user_id)` |

Bearer ativos vivem em `auth_tokens`, separados das identities. Um único `user_id` pode ter `tg + github + google` linkados e múltiplos tokens ativos (um por máquina/CLI session). Observabilidade cruza canais via `user.id` no span (já adicionado no spec MVP).

## Provedores suportados: GitHub e Google

Ambos são suportados no MVP do CLI auth — o usuário escolhe na tela de login.

**GitHub** é o provedor "natural" para o público inicial (devs):

- Devs já estão logados o tempo todo, fricção zero.
- OAuth permite gates futuros por `org membership` ou `team membership` (ex: "só membros de `smsilva/wasp-admins` podem provisionar") — modelo que Google só tem via Workspace.
- Setup: OAuth App em `github.com/settings/developers`. Escopo mínimo: `read:user` (login + email para vincular ao user interno).

**Google** cobre o público "não-dev" e ambientes corporativos:

- Universal — qualquer pessoa com Gmail/Workspace.
- Gates por domínio (`hd=example.com` no OIDC) permitem restringir ao tenant corporativo.
- Setup: OAuth client no Google Cloud Console. Escopo mínimo: `openid email profile`.

Configuração no `.env`:

```
WASP_AGENT_OAUTH_GITHUB_CLIENT_ID=...
WASP_AGENT_OAUTH_GITHUB_CLIENT_SECRET=...
WASP_AGENT_OAUTH_GOOGLE_CLIENT_ID=...
WASP_AGENT_OAUTH_GOOGLE_CLIENT_SECRET=...
```

Provedores ausentes (sem `client_id` configurado) **não aparecem** na tela de login. Operador pode habilitar só um ou os dois.

Vincular múltiplos provedores ao mesmo `user_id` é caso de uso futuro (ex.: um dev usa GitHub no laptop e Google no celular) — possível via endpoint `/cli/link/<provider>` autenticado por Bearer já existente. Fora de escopo do MVP deste spec.

## Fora de escopo

- **`wasp` CLI binário** em si — este spec assume sua existência. Pode ser bash wrapper inicial, Python (`click`/`typer`), ou Go binário. Decisão separada.
- **Refresh tokens** — Bearer simples com TTL longo (30d?) chega; refresh é complexidade prematura.
- **Device code flow** (RFC 8628, sem browser local — útil para ambientes headless como CI). Possível extensão, mas o browser flow cobre 95% dos casos.
- **Auto-signup**: primeiro login por OAuth não cria `user_id` automaticamente — operador precisa pré-vincular a identity GitHub/Google ao user via comando admin (extensão de `make admin-invite`). Justificativa: o controle de acesso fica explícito; auto-signup viraria allowlist aberta para qualquer conta GitHub/Google do mundo.
- **Linkar múltiplos provedores ao mesmo `user_id`** após o primeiro login — `/cli/link/<provider>` é uma evolução natural mas não está neste escopo.
- **Provedores OAuth adicionais** (GitLab, Microsoft, Auth0) — adicionar quando houver demanda concreta. O modelo (`channel="<provider>"` + `auth_tokens`) já comporta sem mudança de schema.
- **2FA / MFA** — irrelevante até o IdP do operador cobrir (GitHub e Google já cobrem).

## Pré-requisitos para promover a Draft

1. Existência de uma `wasp` CLI (mesmo MVP — bash wrapper sobre `local-chat` já é embrião).
2. Decisão sobre Bearer TTL e revogação.
3. Pesquisa do padrão atual no agno: como adicionar middleware de auth no `AgentOS.get_app()` sem fork.
4. Confirmar escopos OAuth mínimos para cada provedor (GitHub: `read:user`? Google: `openid email profile`?).
5. Como passar `user_id` resolvido pelo middleware para o `run_context` que a tool lê.
6. Definir UX da tela de seleção de provedor (botões lado-a-lado? auto-redirect se só um configurado?).

## Relação com o spec MVP

Este spec **estende** o modelo de dados de `2026-05-20-chat-id-allowlist.md`, não substitui:

- Reusa `auth_users` e `auth_identities` (PK composta `(channel, channel_id)` já suporta `channel="github"` e `channel="google"` sem mudança).
- Adiciona `auth_tokens`.
- Reusa o `agent.db`.
- Span attribute `user.id` (já no MVP) passa a refletir o user real via OAuth em vez de `"local-operator"` placeholder.

Quando este spec for `Implemented`, o canal `local` (curl) pode ser deprecado em favor de Bearer autenticado, **ou** manter `local` como conveniência dev-only com a mesma política de trusted-host.

## Decisões fechadas até aqui (conversa de 2026-05-21)

- **Provedores OAuth = GitHub e Google** (operador habilita um ou os dois via `client_id`/`client_secret` no `.env`). Não IdP próprio.
- **Modelo de dados estende o MVP**, não cria tabelas paralelas. `channel="github"` e `channel="google"` reaproveitam `auth_identities`.
- **Bearer em tabela separada `auth_tokens`** — desacopla identidade (quem você é) de credencial ativa (como você está autenticado agora).
- **Browser callback para localhost** é o flow (padrão `gh`/`gcloud`/`flyctl`), não device code flow.
- **Token persistido em `~/.config/wasp/credentials`** com chmod 600.
- **Sem auto-signup**: primeiro OAuth login só funciona se admin pré-vinculou a identity GitHub/Google ao user. Evita allowlist aberta.

## Próximo passo

Promover a Draft quando a `wasp` CLI existir como artefato concreto (mesmo que MVP). Antes disso, ficar como Idea — referência viva para qualquer decisão de auth de canal sem identidade nativa.
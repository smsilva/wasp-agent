# Autenticação multi-canal e allowlist

**Date:** 2026-05-20  
**Updated:** 2026-05-21  
**Status:** Approved  
**Prioridade:** Alta — precede os demais specs abertos em 2026-05-20.

## 1. Contexto

Hoje qualquer `chat_id` do Telegram que conheça o handle do bot pode interagir, invocar `provision_platform_instance` e provisionar tenants no `wasp-gitops`. Não há identidade nem autorização — só a confirmação manual no LLM (system prompt). Vazamento do token do bot = acesso irrestrito.

Embora o bot exponha hoje só o canal Telegram (mais o `local-chat` de dev), o repositório já trata o canal de origem como dimensão de primeira classe (§14 do CLAUDE.md: `Notifier` Protocol selecionando por `extract_channel`). Modelar autorização só em cima de `chat_id` cru repete a dívida que `Notifier` já evitou e força reescrita assim que Discord/Slack entrarem.

Este spec formaliza o item de §9 do CLAUDE.md e desbloqueia a security review (§9a).

## 2. Princípio central

> **O canal autentica. Nós autorizamos.**

Cada canal (Telegram, Slack, Discord, CLI futura) já entrega ao backend uma identidade verificada — `user.id` do Telegram, `member_id` do Slack, etc. Nosso trabalho não é re-autenticar essa identidade, e sim:

1. **Mapear** `(channel, channel_id)` para um `user_id` interno estável.
2. **Autorizar** com base na existência desse mapeamento.
3. **Observar** as ações por `user.id` interno (não pelo `channel_id` cru), de forma que a trilha de audit cruze canais.

Este é o mesmo padrão documentado pela aiogram e pelo exemplo oficial do `pyTelegramBotAPI`: a identidade Telegram do remetente do `/start` é confiável; o trabalho do bot é validar o payload e vinculá-lo a uma conta interna ([aiogram deep linking](https://docs.aiogram.dev/en/latest/utils/deep_linking.html), [pyTelegramBotAPI deep_linking.py](https://github.com/eternnoir/pyTelegramBotAPI/blob/master/examples/deep_linking.py)).

## 3. Onboarding — Nível 1 (escopo deste spec)

### 3.1 Padrão escolhido: invite admin + `/start <token>` deep link

A pesquisa mostrou que **deep link com start payload é o padrão dominante** para vincular um chat Telegram a uma conta interna em sistemas DevOps/SaaS. O fluxo canônico, descrito tanto na [doc oficial do Telegram](https://core.telegram.org/bots/features#deep-linking) quanto nos exemplos do [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/examples/deeplinking.py) e [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI/blob/master/examples/deep_linking.py), é:

1. Sistema externo gera um token único de uso único e vida curta.
2. Token é associado, no backend, a uma conta interna pendente.
3. URL `https://t.me/<BotName>?start=<token>` é entregue ao usuário (e-mail, dashboard, copy/paste).
4. Usuário abre a URL, Telegram lança o bot, manda `/start <token>` automaticamente.
5. Bot valida o token: existe, não expirou, não foi consumido. Se OK, cria/atualiza o mapeamento `(channel="tg", channel_id=<user.id>) → user_id` interno e marca o token como consumido.

Para o `wasp-agent` o "sistema externo" é o próprio operador (admin) chamando uma CLI/Make target. O fluxo termina assim:

```
admin                                wasp-agent                      novo usuário
  | make admin-invite USER=alice         |                                |
  |------------------------------------->|                                |
  |   token=abc123, link=t.me/Bot?start=abc123                            |
  |<-------------------------------------|                                |
  | repassa o link por canal seguro      |                                |
  |---------------------------------------------------------------------->|
  |                                      | <----------- /start abc123 ---|
  |                                      | valida token, cria identity   |
  |                                      | "Bem-vindo, Alice. Você pode  |
  |                                      |  agora provisionar plataformas"
  |                                      |------------------------------>|
```

### 3.2 Por que não Login Widget no MVP

A [Login Widget](https://core.telegram.org/widgets/login) faz sentido quando há um site SSO-style ("Sign in with Telegram"). O `wasp-agent` não tem frontend web — todo o ponto de contato é o próprio bot. Login Widget exigiria publicar um site, configurar `/setdomain` no BotFather e duplicar o flow. Deep link `/start` cobre o caso real com infraestrutura zero.

A pesquisa em integrações Sentry/GitLab confirma: integrações Telegram em produtos DevOps **sempre** começam pela posse do bot token + mapeamento manual de `chat_id`, nunca via Login Widget ([GitLab Telegram integration](https://docs.gitlab.com/user/project/integrations/telegram/)).

### 3.3 Por que não `request_contact` (botão de telefone)

`request_contact` é apropriado para apps consumer que querem o número de telefone como identidade canônica. O `wasp-agent` não usa telefone para nada — adicionaria PII sem benefício e amarraria o modelo a Telegram.

## 4. Modelo de dados

### 4.1 Decisão: reusar `agent.db`

O `agent.db` já existe, já é criado com `umask 077` (permissão 600 — ver `main.py:13`) e já é a fonte da memória de sessão do agno. Criar um SQLite separado dobraria operações (backup, permissão, path) sem ganho. Tabelas novas vivem no mesmo arquivo, em namespace próprio (prefixo `auth_*`), abertas via `sqlite3` direto — não via agno, porque o esquema é nosso, não do framework.

### 4.2 DDL

```sql
CREATE TABLE IF NOT EXISTS auth_users (
  user_id      TEXT PRIMARY KEY,        -- UUID gerado no invite
  display_name TEXT NOT NULL,
  created_at   TEXT NOT NULL            -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS auth_identities (
  channel     TEXT NOT NULL,            -- 'tg', 'slack', 'discord', ...
  channel_id  TEXT NOT NULL,            -- Telegram user.id como string, etc.
  user_id     TEXT NOT NULL REFERENCES auth_users(user_id),
  linked_at   TEXT NOT NULL,
  PRIMARY KEY (channel, channel_id)
);

CREATE INDEX IF NOT EXISTS auth_identities_user_idx
  ON auth_identities(user_id);

CREATE TABLE IF NOT EXISTS auth_invites (
  token       TEXT PRIMARY KEY,         -- URL-safe, 32 bytes random
  user_id     TEXT NOT NULL REFERENCES auth_users(user_id),
  channel     TEXT,                     -- opcional: restringe ao canal
  channel_id  TEXT,                     -- opcional: pré-vincula channel_id específico
  created_by  TEXT NOT NULL,            -- user_id do admin que emitiu
  created_at  TEXT NOT NULL,
  expires_at  TEXT NOT NULL,            -- default: created_at + 24h
  used_at     TEXT                      -- NULL = não consumido
);
```

Notas:

- `auth_users` é cross-canal — um usuário pode ter identidades em Telegram **e** em Slack futuramente, ambas apontando para o mesmo `user_id`.
- `auth_identities` tem chave composta `(channel, channel_id)`: a mesma `channel_id` em canais diferentes é livre, não conflita.
- `auth_invites` opcionalmente pré-vincula a um canal específico (`channel='tg'`) para que o token só funcione em Telegram. O MVP pode emitir invites genéricos.
- Tokens são URL-safe base64 de 32 bytes (`secrets.token_urlsafe(32)`), seguindo a recomendação do aiogram de usar `encode=True` para payloads que vão na URL.

## 5. Mudanças no código

### 5.1 Novo módulo `wasp/auth.py`

API mínima:

```python
def is_authorized(channel: str, channel_id: str) -> str | None:
    """Retorna user_id se autorizado, None caso contrário."""

def redeem_invite(token: str, channel: str, channel_id: str, display_name: str) -> str | None:
    """Consome token e cria identity. Retorna user_id ou None se inválido."""

def create_invite(display_name: str, created_by: str, channel: str | None = None) -> str:
    """Cria user pendente + invite, retorna token."""

def revoke(channel: str, channel_id: str) -> bool:
    """Remove identity. Mantém o user_id para audit. Retorna True se removeu."""
```

Conexão `sqlite3` própria, com `PRAGMA journal_mode=WAL` (já é o que o agno usa em SqliteDb). DDL idempotente (`CREATE TABLE IF NOT EXISTS`) executada na primeira chamada.

### 5.2 Onde a verificação entra

Hoje, agno encaminha cada update Telegram diretamente ao agente. Há duas opções:

**Opção A — Middleware antes do agno** (preferida). Interceptar o webhook Telegram antes de `AgentOS.get_app()` despachar para o agente. Vantagem: o agno nem é invocado para usuários não autorizados, economiza tokens LLM. Desvantagem: requer entender como `agno.os.interfaces.telegram.Telegram` expõe seus handlers.

**Opção B — Guarda dentro da tool** (`provision_platform_instance`). Bloqueia o efeito colateral mas o LLM ainda processa a mensagem. Mais barato de implementar, pior em custo e em UX.

Decisão tentativa: **A**, com fallback B se o agno não permitir interceptar limpo. A escolha final cai no plano de execução.

O handler de `/start <token>` também precisa ser registrado — provavelmente como uma rota custom anexada ao `app` em `main.py`, análoga ao `metrics_endpoint` já existente.

### 5.3 CLI admin

Make target chamando script em `scripts/` (§15 do CLAUDE.md). Sketch:

```
make admin-invite NAME="Alice"          # imprime token + link t.me/Bot?start=<token>
make admin-revoke CHANNEL=tg ID=12345
make admin-list                          # lista identities ativas
```

Os scripts (`scripts/admin-invite`, etc.) abrem `agent.db` direto via `sqlite3` e chamam `wasp.auth`. Não passam pelo bot — administração é offline, do host onde o bot roda.

## 6. Configuração

Novas variáveis (todas com prefixo `WASP_AGENT_`, §17 do CLAUDE.md):

| Variável | Default | Função |
|---|---|---|
| `WASP_AGENT_DB_FILE` | `agent.db` | Path do SQLite (já implícito hoje, formalizar). |
| `WASP_AGENT_INVITE_TTL_HOURS` | `1` | Janela de validade do token de invite. |
| `WASP_AGENT_BOOTSTRAP_ADMIN` | — (vazio) | Ver §11.1. |

Não há `WASP_AGENT_ALLOWED_CHAT_IDS` — allowlist é dinâmica e vive no banco.

## 7. Observabilidade

Spans hoje carregam `platform.name` e `watcher.spawned`. Adicionar:

- `user.id` (interno) em todo span do fluxo de provisioning e do watcher.
- `auth.channel` (`tg`, `slack`, ...) — desacopla o tipo de canal do conteúdo do `channel_id`.
- **Não** logar `channel_id` cru em atributos de span. `channel_id` Telegram não é segredo, mas vincular logs a `user.id` interno facilita correlação cross-canal futura.

## 8. Telemetria de negação

Métrica Prometheus nova:

```
wasp_auth_denied_total{channel="tg", reason="unknown_identity|invite_expired|invite_consumed"}
```

Log estruturado em nível `WARNING` por negação, com `channel`, `channel_id` (em log, ok), e `reason`. Servirá para detectar tentativa de abuso e diagnosticar invites mal entregues.

## 9. Fora de escopo (futuros specs)

- **Nível 2 — OAuth** (GitHub/Google) para auto-onboarding sem admin. Modelo de dados já comporta: nova linha em `auth_identities` com `channel='github'`.
- **Nível 3 — CLI device flow** (estilo `gh auth login`) para integrações server-to-server.
- **Multi-tenancy real**: hoje todo `user_id` autorizado pode provisionar qualquer tenant. Granularidade (RBAC, namespace por user) é spec separado.
- **Rate limiting** por `user_id`.
- **Rotação/expiração de identities** (forçar re-login após N dias).
- **2FA** — irrelevante até existir um vetor de ataque que o canal não cubra.

## 10. Alternativas consideradas e descartadas

### 10.1 Env var estática `ALLOWED_CHAT_IDS=123,456`

Originalmente sugerida na versão `Idea`. Problemas:
- Onboarding manual (admin precisa coletar `chat_id` do usuário primeiro, fora de banda).
- Acoplada a Telegram — adicionar Slack significa nova env var.
- Mudança requer restart.
- Não registra "quem é" o `chat_id` (sem `display_name`, sem `created_at`).

A pesquisa confirmou que esse padrão existe (ex.: configs `allowFrom`/`allowed_users` em bots self-hosted simples como OpenClaw) mas é descrito como a fonte mais comum de bot silencioso por má configuração ([Stack Junkie](https://www.stack-junkie.com/blog/fix-openclaw-telegram-errors)). Inviável para o nosso modelo de crescer canais.

### 10.2 Arquivo YAML `allowlist.yaml`

Mesma classe de problema da env var, com a vantagem marginal de não exigir restart se for relido. Continua sem registro temporal, sem invite, sem audit.

### 10.3 Telegram Login Widget no MVP

Descartada por exigir site web (que não temos) e `setdomain` no BotFather. Vide §3.2.

### 10.4 Allowlist por `chat_id` puro (sem tabela `auth_users`)

Tentação: pular `auth_users` e usar `(channel, channel_id)` como PK direta. Decidido contra — quebra o princípio §2 (autorizar por `user.id` interno) e força reescrita assim que entra o segundo canal. O custo de uma tabela a mais é zero; o custo de mudar de modelo no meio do projeto não é.

## 11. Riscos e decisões pendentes

### 11.1 Bootstrap do primeiro admin

Não há admin no banco vazio → ninguém pode emitir o primeiro invite via `make admin-invite` (que precisa registrar `created_by`). Opções:

- **a)** Env var `WASP_AGENT_BOOTSTRAP_ADMIN=<channel>:<channel_id>:<display_name>` lida no startup; se a tabela `auth_identities` estiver vazia, cria esse usuário como admin e ignora a env nas execuções subsequentes.
- **b)** Script `scripts/admin-bootstrap` que, se chamado e a tabela estiver vazia, recebe args e cria o primeiro admin. Falha se a tabela já tem registros.
- **c)** Aceitar o primeiro `/start` sem token e promover esse usuário a admin (TOFU — trust on first use). Inseguro: vazamento do token do bot durante a janela de bootstrap = atacante toma o admin.

**Decidido:** (b). Operação explícita, sem dependência de env em runtime, sem janela TOFU.

### 11.2 Negação silenciosa vs. mensagem explícita

A pesquisa mostrou que **silent ignore + log server-side é o padrão dominante** para bots privados ([Stack Junkie](https://www.stack-junkie.com/blog/fix-openclaw-telegram-errors); a própria doc do Telegram, em outro contexto, recomenda evitar exibir certos erros ao usuário — [Telegram API errors](https://core.telegram.org/api/errors)).

Argumento contra silêncio total: usuário legítimo que recebeu o link e clica em algo errado (token expirado, copy/paste truncado) fica sem feedback e abre suporte com o admin. Em DevOps bots privados a fricção de suporte é tolerável; em consumer bots não.

**Decidido:** silêncio total para `chat_id` sem identidade. Para `/start <token>` inválido/expirado/consumido, responder com uma mensagem genérica ("Link inválido ou expirado. Solicite um novo ao administrador.") — o atacante já sabe que existe um bot (clicou no link), revelar que o token foi rejeitado não vaza nada novo, e o usuário legítimo precisa do feedback.

### 11.3 Expiração e rotação de invites

**Decidido:** 1h. O fluxo "admin gera → manda por DM → usuário clica" cabe nessa janela. Se o usuário não usar a tempo, admin emite outro — operação barata.

### 11.4 Revogação atômica

Quando admin revoga (`make admin-revoke`), existem sessões agno em curso para aquele `chat_id`. A verificação de §5.2 (middleware antes do agno) garante que mensagens futuras sejam barradas, mas uma tool já em execução (`provision_platform_instance` que demora 30s) não é interrompida. **Decidido:** aceitável para MVP como limitação conhecida — documentar no runbook.

## 12. Próximo passo

Plano de execução em `docs/sdlc/03-execution/2026-05-21-auth-multichannel-plan.md` cobrindo:

1. Esquema + `wasp/auth.py` + testes (100% coverage, §5 do CLAUDE.md).
2. Middleware de verificação no entrypoint do webhook.
3. Handler `/start <token>` + integração com o bot.
4. CLI admin (`scripts/admin-invite`, `admin-revoke`, `admin-list`) + Make targets.
5. Span attribute `user.id` + métrica Prometheus de negação.
6. Bootstrap admin (`scripts/admin-bootstrap`).
7. Runbook em `docs/runbooks/` para o operador (como emitir invite, como revogar).

## 13. Achados que questionam decisões prévias

A pesquisa não contradiz nenhuma das decisões fechadas na conversa anterior. Dois pontos a marcar para revisão:

- **Recusa silenciosa (decisão tentativa #6)**: a pesquisa apoia silêncio para `chat_id` desconhecido **mas** sugere resposta explícita para token de invite inválido — vide §11.2. Refino, não contradição.
- **Reuso do `agent.db`**: não encontrei pesquisa que questione. O risco potencial é colisão de schema com upgrades futuros do agno — mitigado pelo prefixo `auth_*` em todas as tabelas próprias.
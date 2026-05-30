# Auth admin workflow

Como autorizar usuários no `wasp-agent` via allowlist multi-canal.

## Pré-requisito

O operador precisa do par `(channel, channel_id)` do primeiro admin.

Para Telegram, descobrir seu próprio `user.id`:

1. Abrir o Telegram e mandar qualquer mensagem para [@userinfobot](https://t.me/userinfobot).
2. O bot responde com seu `Id` numérico. Copiar esse número — é o `channel_id` para `CHANNEL=tg`.

## Bootstrap inicial

Uma única vez por deploy, com a tabela `auth_users` vazia:

```bash
make admin-bootstrap NAME="Silvio" CHANNEL=tg ID=12345678
```

Falha se já existir qualquer usuário. Esse comando cria o primeiro admin sem exigir convite.

## Convidar novo usuário

```bash
make admin-invite NAME="Alice"
```

A saída inclui:

```
Token: <urlsafe>
Link: https://t.me/<Bot>?start=<token>
```

O operador repassa o link via canal seguro (DM, e-mail). O link é válido por 1h (configurável via `WASP_AGENT_INVITE_TTL_HOURS`) e só pode ser consumido uma vez.

`TELEGRAM_BOT_USERNAME` precisa estar setado no `.env` para o link ser montado corretamente.

## Usuário consome o link

1. Usuário clica no link.
2. Telegram abre o chat com o bot.
3. Bot recebe `/start <token>` automaticamente.
4. Bot responde: `Bem-vindo, Alice. Você está autorizado a usar o wasp-agent.`

Se o token expirou, já foi consumido, ou é inválido, o bot responde: `Link inválido ou expirado. Solicite um novo ao administrador.`

## Vincular canal adicional a usuário existente

Quando o mesmo operador quer usar outro canal (ex.: Discord) sem perder o histórico do canal original:

```bash
# 1. Descobrir o user_id atual
make admin-list

# 2. Vincular o novo canal ao mesmo user_id
make admin-link USER_ID=694ba973edf3488bb3f6ba38c51e6aae CHANNEL=dc ID=708384119989600337
```

Regras:
- O `user_id` deve existir em `auth_users` (obtido via `make admin-list`).
- O par `(channel, channel_id)` não pode estar já vinculado.
- Não há TTL — o vínculo é permanente até `make admin-revoke`.

**Como descobrir o `channel_id` por canal:**

| Canal | Como obter |
|-------|-----------|
| Telegram | Mandar mensagem para [@userinfobot](https://t.me/userinfobot) — campo `Id` |
| Discord | Ativar "Modo Desenvolvedor" em Configurações → Avançado, clicar com botão direito no avatar → "Copiar ID do Usuário" |

## Listar identidades ativas

```bash
make admin-list
```

## Revogar

```bash
make admin-revoke CHANNEL=tg ID=12345678
```

Remove a identidade da allowlist mas mantém o registro em `auth_users` para audit. Sessões agno em curso para aquele `chat_id` **não** são interrompidas — limitação conhecida.

## Diagnóstico — `chat_id` não autorizado

Logs estruturados registram cada negação em nível `WARNING` com a mensagem `auth denied: channel=tg channel_id=...`.

Para inspecionar:

```bash
# Se LOG_FILE estiver configurado
grep "auth denied" logs/wasp.jsonl

# Caso contrário, no stdout do `make run`
```

Métrica Prometheus `wasp_auth_denied_total{channel,reason}` disponível se `PROMETHEUS_METRICS_ACTIVE=true`.

## Canal `local` (local-chat / E2E)

O canal `local` **não** passa por allowlist — é tratado como "operador confiável no host". O boundary de segurança é a rede: o endpoint AgentOS (`/agents/.../runs`) deve ouvir só `127.0.0.1` em produção.

Se for necessário expor `local-chat` por rede, ver spec futuro `docs/sdlc/02-design/2026-05-21-cli-device-flow-oauth.md`.

## Configuração de backend

O acesso a dados de auth é abstraído via `AuthRepository` (Protocol em `wasp/auth/protocol.py`). Backend selecionado por env var:

| Env var | Default | Valores | Efeito |
|---------|---------|---------|--------|
| `WASP_AGENT_DB_BACKEND` | `sqlite` | `sqlite` | Usa `SqliteAuthRepository` apontando para `WASP_AGENT_DB_FILE` (default `agent.db`). Outros valores levantam `ValueError`. |
| `WASP_AGENT_DB_FILE` | `agent.db` | path | Arquivo SQLite. Ignorado se o backend não for `sqlite`. |
| `WASP_AGENT_INVITE_TTL_HOURS` | `1` | int | TTL do invite gerado por `make admin-invite`. |

Implementações adicionais (ex: Postgres gerenciado) seguem o Protocol e são registradas em `wasp/auth/__init__.py::get_repository()`.

## Limitações conhecidas

- **TTL 1h** (configurável). Se o link expirar antes do uso, admin emite um novo invite.
- **Revogação não interrompe tools em execução** — só impede novas mensagens daquele `chat_id`.
- **Sem multi-tenancy real** — qualquer usuário autorizado pode provisionar qualquer tenant.
- **Bootstrap exige DB vazio** — para rotacionar o admin inicial, revogar manualmente via SQL em `agent.db` ou apagar o arquivo e refazer o bootstrap.
- **`make admin-link` exige `user_id` conhecido** — obtenha via `make admin-list` antes de vincular.

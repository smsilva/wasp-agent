# Smoke test Telegram — manual, sem cluster

Valida o canal Telegram + auth multi-canal + comportamento do LLM. **Não exige cluster nem provisionamento real.**

O que esse smoke test cobre:

- Webhook do Telegram chega ao agente via ngrok
- Validação do `X-Telegram-Bot-Api-Secret-Token`
- Deep link `/start <token>` consome invite e autoriza o `chat_id`
- Auth guard em `provision_platform_instance` (allow para chat autorizado, deny silencioso para os demais)
- Agente processa e responde
- LLM segue o system prompt (em especial: pede confirmação antes de `provision_platform_instance`)
- Memória de sessão (`add_history_to_context=True`)
- Notifier Telegram escreve de volta no chat

## Setup de infraestrutura (uma vez por máquina)

Seguir [`telegram-local-dev.md`](telegram-local-dev.md):

1. Bot criado no `@BotFather`, com `TELEGRAM_TOKEN` no `.env`.
2. `TELEGRAM_WEBHOOK_SECRET_TOKEN` gerado e no `.env`.
3. `TELEGRAM_BOT_USERNAME` no `.env` — sem o `@`, ex: `wasp_local_bot`. Usado para montar o link `https://t.me/<bot>?start=<token>`.
4. ngrok rodando + webhook registrado no Telegram com path `/telegram/webhook`.

## Descobrir seu `user.id` do Telegram

Abrir [@userinfobot](https://t.me/userinfobot) e enviar qualquer mensagem. Anotar o `Id` numérico — é o `channel_id` do canal `tg`.

## Inicializar o agente

```bash
make run     # agente local na porta 7777
```

O `init_db()` cria as tabelas `auth_*` no `agent.db` na primeira inicialização. Deixar rodando em primeiro plano para acompanhar os logs.

## Setup de auth — escolher um dos dois fluxos

**Fluxo 1: bootstrap (primeiro deploy, tabela vazia)**

Em outro terminal:

```bash
make admin-bootstrap NAME="Você" CHANNEL=tg ID=<seu user.id>
```

Saída esperada: `Bootstrapped user: <uuid>`. Falha se já existir qualquer usuário — nesse caso, use o Fluxo 2 ou apague `agent.db` (ver Reset de estado).

**Fluxo 2: invite + deep link (admin já existe; novo usuário entrando)**

```bash
make admin-invite NAME="Você"
```

Saída inclui `Token: <urlsafe>` e `Link: https://t.me/<bot>?start=<token>`. Clicar no link no Telegram. O bot deve responder:

```
Bem-vindo, Você. Você está autorizado a usar o wasp-agent.
```

Se aparecer `Link inválido ou expirado.`, verificar:

- TTL expirou (default 1h, ajustável via `AGENT_INVITE_TTL_HOURS`)
- Token já consumido — gerar novo invite
- `TELEGRAM_BOT_USERNAME` no `.env` aponta para o bot certo

Confirmar a inserção:

```bash
make admin-list
```

Deve listar `tg`, seu `user.id`, e o `display_name`.

## Roteiro do smoke test

No chat do Telegram:

1. `"oi"` → bot responde (chat normal).
2. `"Meu nome é João."` depois `"Qual é o meu nome?"` → bot lembra (memória de sessão, `add_history_to_context=True`).
3. `"Criar uma plataforma chamada test"` → bot **pede confirmação**, não chama a tool sozinho.
4. `"não, cancela"` → bot não chama a tool.

Os passos 1–4 cobrem o que muda com mais frequência (system prompt, wiring do Telegram, formato de respostas, auth allow path). Se você **confirmar** o pedido no passo 3, a tool roda de verdade — sem cluster nem GitHub configurado, isso falha. Para o smoke test puro, basta recusar.

## Verificar o auth deny path (opcional, recomendado depois de mudar `provision.py` ou `auth.py`)

Pedir a alguém com outro `chat_id` (não autorizado) que envie qualquer mensagem ao bot. Resultado esperado:

- O LLM responde normalmente em mensagens conversacionais.
- Mas se essa pessoa pedir `"criar plataforma X"` e **confirmar**, a tool retorna `{"status": "unauthorized", "message": "Acesso negado."}`. O bot relata isso ao usuário.

Validar nos logs do `make run` (ou em `logs/wasp.jsonl` se `LOG_FILE` estiver setado):

```bash
grep "auth denied" logs/wasp.jsonl  # ou stdout do agente
```

Deve aparecer `auth denied: channel=tg channel_id=<outro id>`.

Se `PROMETHEUS_METRICS_ACTIVE=true`:

```bash
curl -s http://localhost:7777/telemetry/prometheus | grep wasp_auth_denied_total
```

Deve incrementar `wasp_auth_denied_total{channel="tg",reason="unknown_identity"}`.

## Reset de estado (refazer bootstrap)

`make admin-bootstrap` recusa rodar com a tabela populada. Para zerar:

```bash
rm agent.db
make run    # init_db recria as tabelas vazias
make admin-bootstrap NAME="..." CHANNEL=tg ID=<id>
```

`agent.db` guarda também a memória das sessões agno — apagar perde todo o histórico de conversas anteriores. Em produção, prefira `make admin-revoke` + novo `make admin-invite`.

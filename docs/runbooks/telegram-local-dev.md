# Telegram — Desenvolvimento local

Como testar o bot Telegram localmente usando ngrok como túnel público.

> **Escopo**: setup de Telegram + ngrok para o smoke test do bot (caminho B em [`validation.md`](validation.md)). O smoke test **não exige cluster** — basta `make run`. Cluster GitOps só entra na validação fim-a-fim do ciclo de provisionamento (apêndice em `validation.md`).

---

## Pré-requisitos

- ngrok instalado (`snap install ngrok` ou https://ngrok.com/download)
- `.env` preenchido com `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `TELEGRAM_TOKEN` e `TELEGRAM_BOT_USERNAME` (sem o `@`)
- Bot criado no `@BotFather` (envie `/newbot` para obter o `TELEGRAM_TOKEN`)

> Este runbook cobre o setup de túnel + webhook. O smoke test propriamente dito (incluindo auth via `make admin-bootstrap` ou `/start <token>`) está em [`validation.md` §B](validation.md#b-smoke-test-telegram--manual-sem-cluster).

---

## 1. Gerar o TELEGRAM_WEBHOOK_SECRET_TOKEN

O agno exige esse token para validar que os requests vêm do Telegram (não de terceiros). Gere um valor aleatório seguro:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Adicione ao `.env`:

```
TELEGRAM_WEBHOOK_SECRET_TOKEN=<valor gerado>
```

---

## 2. Expor o localhost com ngrok

```bash
ngrok http 7777
```

Anote a URL pública exibida, ex: `https://abc123.ngrok-free.app`.

> A URL muda a cada vez que o ngrok reinicia na conta gratuita. Repita o passo 3 sempre que isso acontecer.

---

## 3. Registrar o webhook no Telegram

```bash
TELEGRAM_WEBHOOK_URL=${NGROK_URL} # replace with your URL from step 2

cat <<EOF
TELEGRAM_BOT_USERNAME.........: ${TELEGRAM_BOT_USERNAME}
TELEGRAM_TOKEN................: ${TELEGRAM_TOKEN:0:4}
TELEGRAM_WEBHOOK_URL..........: ${TELEGRAM_WEBHOOK_URL}
TELEGRAM_WEBHOOK_SECRET_TOKEN.: ${TELEGRAM_WEBHOOK_SECRET_TOKEN:0:4}
EOF

curl \
  --request POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
  --header "Content-Type: application/json" \
  --data @- <<EOF
{
  "url": "${TELEGRAM_WEBHOOK_URL}/telegram/webhook",
  "secret_token": "${TELEGRAM_WEBHOOK_SECRET_TOKEN}"
}
EOF
```

Resposta esperada:
```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

---

## 4. Iniciar o agente

```bash
make run
```

O agente deve carregar o `.env` com o `TELEGRAM_WEBHOOK_SECRET_TOKEN`. Se o agente já estava rodando antes de adicionar a variável, reinicie-o.

---

## 5. Verificar status do webhook

```bash
curl -s "https://api.telegram.org/bot<TELEGRAM_TOKEN>/getWebhookInfo" | python3 -m json.tool
```

Verifique:
- `url` aponta para sua URL ngrok
- `pending_update_count` é 0 (mensagens pendentes entregues)
- `last_error_message` ausente (sem erros)

Erros comuns:

| Erro | Causa |
|------|-------|
| `502 Bad Gateway` | Agente não está rodando na porta 7777 |
| `Wrong response from the webhook: 403` | `TELEGRAM_WEBHOOK_SECRET_TOKEN` diverge entre `.env` e o webhook registrado |
| `500 Internal server error` | `TELEGRAM_WEBHOOK_SECRET_TOKEN` não está no `.env` do processo em execução |

---

## 6. Verificar setup (chat básico)

Envie qualquer mensagem ao bot no Telegram. Para verificar memória de sessão:

1. `"Meu nome é João."`
2. `"Qual é o meu nome?"`

A segunda resposta deve mencionar "João" — confirma que `add_history_to_context=True` e o SQLite estão funcionando.

> Este passo valida apenas o canal Telegram (webhook + LLM + memória). Mensagens conversacionais não exigem auth. Para testar o fluxo completo — incluindo `provision_platform_instance` — continue em [`validation.md §B`](validation.md#b-smoke-test-telegram--manual-sem-cluster), que cobre auth bootstrap, roteiro de provisionamento e, opcionalmente, o ciclo GitOps completo até `Ready`.

---

## Quando a URL do ngrok mudar

Apenas repita o passo 3 com a nova URL. Não é necessário reiniciar o agente nem regenerar o secret token.

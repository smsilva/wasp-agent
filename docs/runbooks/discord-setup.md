# Discord — Setup e autorização de usuários

Como configurar o bot Discord e autorizar usuários (admin e convidados).

> **Escopo**: setup inicial + fluxo de auth Discord. O smoke test completo (LLM + memória) está em [`validation-discord.md`](validation-discord.md) (a criar).

---

## Pré-requisitos

- `.env` preenchido com `DISCORD_APP_TOKEN`
- Bot criado no [Discord Developer Portal](https://discord.com/developers/applications)
- Bot adicionado ao servidor com permissões `Send Messages` + `Read Message History`
- Intents habilitados no portal: **Message Content Intent** (Settings → Bot → Privileged Gateway Intents)

---

## 1. Configurar o bot no Discord Developer Portal

1. Criar uma Application em `https://discord.com/developers/applications`.
2. Em **Bot**: clicar em "Reset Token", copiar o token → `DISCORD_APP_TOKEN` no `.env`.
3. Ainda em **Bot**: habilitar **Message Content Intent**.
4. Em **OAuth2 → URL Generator**: marcar `bot` + permissões `Send Messages`, `Read Message History`. Usar a URL gerada para adicionar o bot ao servidor.

---

## 2. Descobrir o Discord user ID

Necessário para `make admin-bootstrap` e `make admin-link`.

1. No Discord: **Configurações do usuário → Avançado → Modo Desenvolvedor** (ativar).
2. Clicar com botão direito no próprio avatar (ou no avatar de qualquer usuário) → **Copiar ID do Usuário**.

O ID é um número de 18 dígitos, ex: `708384119989600337`.

---

## 3. Bootstrap do admin

Uma única vez, com o banco vazio:

```bash
make admin-bootstrap NAME="Silvio" CHANNEL=dc ID=708384119989600337
```

Falha se já existir qualquer usuário. Cria o primeiro admin sem exigir convite.

---

## 4. Iniciar o agente

```bash
make run
```

Aguardar a linha:

```
Shard ID None has connected to Gateway
```

---

## 5. Verificar que o bot está respondendo

Abrir o DM com o bot no Discord e enviar qualquer mensagem. O bot deve responder.

Se não responder, verificar:

| Sintoma | Causa provável |
|---------|----------------|
| Sem resposta, sem log | Message Content Intent não habilitado no portal |
| Log `auth denied` | `(dc, <user_id>)` não está na allowlist — ver seção 6 |
| Log `DISCORD_APP_TOKEN` error | Token inválido ou não setado no `.env` |

---

## 6. Autorizar usuários adicionais

O Discord não tem deep link de convite como o Telegram. O admin precisa obter o Discord user ID do convidado (instrução na seção 2) e vinculá-lo manualmente.

### Novo usuário (sem conta no sistema)

```bash
# 1. Criar convite com user já registrado (não há fluxo de redemption por DM no Discord)
make admin-invite NAME="Alice"
# Saída inclui o user_id criado — anote

# 2. Vincular identidade Discord ao user_id gerado
make admin-link USER_ID=<user_id_do_invite> CHANNEL=dc ID=<discord_user_id_da_alice>
```

### Usuário existente (já autorizado em outro canal, ex: Telegram)

```bash
# 1. Obter o user_id atual
make admin-list

# 2. Vincular canal Discord ao mesmo user_id
make admin-link USER_ID=<user_id> CHANNEL=dc ID=<discord_user_id>
```

---

## 7. Listar e revogar

```bash
# Ver todas as identidades ativas
make admin-list

# Revogar acesso Discord de um usuário
make admin-revoke CHANNEL=dc ID=<discord_user_id>
```

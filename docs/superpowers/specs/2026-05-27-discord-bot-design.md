# Discord Bot — Design

**Status:** Approved  
**Date:** 2026-05-27  
**Scope:** Mensagens livres no Discord com paridade funcional ao Telegram (auth por invite, watcher, memória por usuário). Slash commands fora de escopo — ver `docs/sdlc/02-design/2026-05-27-discord-slash-commands.md`.

---

## Contexto

O wasp-agent já integra Telegram via `agno.os.interfaces.telegram`. O Discord não tem interface nativa no agno — a integração é implementada manualmente com discord.py, seguindo o padrão `wasp/clients/<canal>/`.

---

## Arquitetura

O Discord usa WebSocket Gateway permanente (discord.py), enquanto o Telegram usa webhooks HTTP. Por isso o Discord **não pode ser registrado como interface agno** no `AgentOS(interfaces=[...])`. Em vez disso, o bot é iniciado como background task asyncio no evento de startup do FastAPI.

```
main.py
├── AgentOS ← [TelegramInterface]     (agno nativo, sem mudança)
└── DiscordBot.start()                (asyncio task no app lifespan)
      └── on_message(msg)
            ├── auth.is_authorized("dc", user_id)
            ├── notifier.register(user_id, channel)
            └── agent.arun(session_id="dc:wasp-agent:<user_id>")
                  └── resposta → channel.send()
```

**Session ID:** `dc:<agent_name>:<user_id>` — mesma estrutura do Telegram (`tg:wasp-agent:<chat_id>`). Garante sessão isolada por usuário Discord.

---

## Componentes

### `wasp/clients/discord/bot.py`

Subclasse de `discord.Client`. Método `on_message`:

1. Ignora mensagens do próprio bot (`msg.author == client.user`).
2. Ignora mensagens sem texto.
3. Verifica `auth.is_authorized("dc", str(msg.author.id))` — retorna sem resposta se não autorizado (mesmo comportamento silencioso do Telegram).
4. Registra `user_id → channel` no `DiscordNotifier`.
5. Chama `await agent.arun(msg.content, session_id=f"dc:wasp-agent:{msg.author.id}")`.
6. Envia resposta com `await msg.channel.send(response)`.

O `DiscordBot` recebe `agent` e `notifier` no construtor — sem acoplamento a globals.

### `wasp/clients/discord/notifier.py`

`DiscordNotifier` mantém `dict[str, discord.TextChannel]` (user_id → canal). Método `send(user_id, text)` envia para o canal registrado; descarta silenciosamente se o usuário nunca mandou mensagem nesta sessão (mesmo comportamento do `ConsoleNotifier` quando sem canal).

### `wasp/clients/discord/__init__.py`

Re-exports: `DiscordBot as DiscordBot`, `DiscordNotifier as DiscordNotifier`.

### `wasp/clients/interfaces.py`

`InterfaceLoader` ganha método `build_discord() -> DiscordBot | None`:

- Lê `DISCORD_APP_TOKEN` do ambiente; retorna `None` se ausente (opt-in idêntico ao Telegram).
- Instancia `DiscordNotifier` e `DiscordBot(agent, notifier)`.
- Armazena ambos em atributos (`self.discord_bot`, `self.discord_notifier`) para uso posterior.
- Retorna o `DiscordBot` — quem registra o lifecycle é `create_app()` em `main.py`, após ter o `app`.

Em `main.py::create_app()`:

```python
loader = InterfaceLoader(agent)
agent_os = AgentOS(agents=[agent], interfaces=loader.build())
app = agent_os.get_app()
bot = loader.build_discord()
if bot:
    app.add_event_handler("startup", bot.start_background)
    app.add_event_handler("shutdown", bot.close)
```

### `wasp/watcher.py` — `_select_notifier`

Adiciona caso `"dc"` ao roteamento por canal:

```python
elif channel == "dc":
    kind = "discord"
```

Resolve `kind == "discord"` para o `DiscordNotifier` singleton armazenado em `wasp.clients.discord._notifier` (módulo-level ref, definida por `InterfaceLoader.build_discord()` após construção). `_select_notifier` lê essa ref — mesmo padrão usado pelo `TelegramNotifier` que lê `TELEGRAM_TOKEN` do ambiente em tempo de execução.

---

## Walk Skeleton

O primeiro slice entrega o caminho vertical mínimo:

1. Bot conecta ao Discord Gateway.
2. Usuário autorizado envia mensagem.
3. Agente responde no mesmo canal.

Auth e watcher integrados na mesma PR (não são opcionais para um slice seguro).

---

## Dependências

Adicionar ao `pyproject.toml`:

```toml
"discord.py>=2.3.0",
```

Sem extra agno — discord.py é dependência direta.

---

## Testes

**Unit (`tests/test_discord_bot.py`):**
- `on_message` com usuário autorizado → `agent.arun` chamado, resposta enviada.
- `on_message` com bot próprio → ignorado.
- `on_message` com usuário não autorizado → `agent.arun` não chamado.
- `DiscordNotifier.send` com canal registrado → `channel.send` chamado.
- `DiscordNotifier.send` com user_id desconhecido → descarta silenciosamente.

Todos com `AsyncMock` — sem conexão real ao Discord. `mock_agno` fixture existente cobre o agente.

**E2E:** O E2E existente não muda. Discord é opt-in via `DISCORD_APP_TOKEN`.

---

## Configuração

Variáveis de ambiente (já presentes no `.env`):

| Variável | Uso |
|---|---|
| `DISCORD_APP_TOKEN` | Token do bot (ativa a integração) |
| `DISCORD_APP_PUBLIC_KEY` | Reservado para slash commands futuros |
| `DISCORD_APP_ID` | Reservado para slash commands futuros |
| `DISCORD_APP_CLIENT_SECRET` | Reservado para OAuth futuro |

---

## Futuro

Slash commands: ver `docs/sdlc/02-design/2026-05-27-discord-slash-commands.md`.
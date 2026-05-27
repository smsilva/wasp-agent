# Discord Slash Commands

**Status:** Idea  
**Date:** 2026-05-27  
**Depende de:** `docs/sdlc/02-design/archived/2026-05-27-discord-bot-design.md` (mensagens livres implementadas)

## Contexto

Extensão do Discord bot para adicionar slash commands (`/provisionar`, `/status`, etc.) com descobribilidade nativa no Discord. O Discord entrega slash commands via HTTP Interactions Endpoint (não WebSocket) — requer endpoint público com verificação de assinatura Ed25519 usando `DISCORD_APP_PUBLIC_KEY`.

## Escopo (ideia preliminar)

- Registrar application commands via Discord API (global ou por servidor).
- Endpoint `/discord/interactions` no FastAPI para receber os payloads.
- Verificação de assinatura com `DISCORD_APP_PUBLIC_KEY`.
- Commands candidatos: `/provisionar <nome>`, `/status`, `/ajuda`.
- Auth por allowlist existente (`auth.is_authorized`).

## Referências

- Discord Interactions docs: https://discord.com/developers/docs/interactions/application-commands
- `DISCORD_APP_ID` e `DISCORD_APP_PUBLIC_KEY` já disponíveis no `.env`.
# wasp/clients/discord

## Lifespan integration with AgentOS

agno sets a `lifespan` context manager on the FastAPI app returned by `agent_os.get_app()`. FastAPI ignores `on_startup`/`on_shutdown` handlers when `lifespan` is set — including `app.router.on_startup.append(fn)`. Also, `FastAPI.add_event_handler` no longer exists as of 0.136.1.

To hook the Discord bot lifecycle: capture `app.router.lifespan_context`, define a new `@asynccontextmanager` that schedules the bot with `asyncio.ensure_future` and delegates to the original, then assign back. See `main.py::create_app`.

## Cross-loop `channel.send` from watcher thread

The watcher runs `asyncio.run(watch_platform(...))` in a dedicated thread with its own event loop. discord.py's `channel.send()` uses an aiohttp session tied to the Discord client's loop (the main FastAPI loop). Calling `await channel.send(text)` from the watcher loop raises `RuntimeError: Timeout context manager should be used inside a task`.

Fix in `DiscordNotifier.send()`: store the Discord loop via `set_loop()` (called from `on_ready`). When `self._loop != asyncio.get_running_loop()`, use `asyncio.run_coroutine_threadsafe(channel.send(text), self._loop)` and await via `run_in_executor(None, future.result)`.

## Mocking in tests — `discord.Client` can't be MagicMock

When mocking the `discord` module as `MagicMock`, `discord.Client` is a MagicMock instance and can't be a base class. In `conftest.py`, install a plain stub class and assign it to `discord_mock.Client`. Include `async def close(self)` on the stub.

Ao testar o branch cross-loop de `DiscordNotifier.send()` com `run_coroutine_threadsafe` mockado, o `channel` deve ser `MagicMock` (não `AsyncMock`): `channel.send(text)` é entregue ao mock e nunca aguardado, então um `AsyncMock` deixa uma corotina pendente que `filterwarnings=error::RuntimeWarning` transforma em falha.

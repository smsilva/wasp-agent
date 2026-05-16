# Handoff

## Goal

Implementar um agente DevOps multi-canal: Telegram bot com Agno Agent que provisiona instâncias de plataforma via GitOps (Crossplane + `smsilva/wasp-gitops`), com memória de sessão e suporte futuro a Discord/Slack.

## Current Progress

**Ciclos 1, 2 e 3 completos. Smoke test end-to-end do watcher validado em 2026-05-16.** O loop completo (Telegram → GitHub commit → ArgoCD sync → Crossplane reconcile → watcher detecta Ready → notificação Telegram) fecha em < 1 min.

Há correções pós-smoke **não commitadas** em `dev` (5 arquivos modificados). 22 testes, 100% cobertura mantida.

### Estado dos ciclos
- **Ciclo 1** — mergeado em `main`. Agent + Telegram interface + SQLite.
- **Ciclo 2** — mergeado em `main`. `provision_platform_instance` tool + Pydantic models + commit GitOps.
- **Ciclo 3** — mergeado em `main` (commits `8e11be8` → `c335345`). Watcher async, polling de Platform CR, notificação Telegram.

### Correções pós-smoke (uncommitted em `dev`)
- `tools/provision.py` — spawn do watcher via `threading.Thread(target=asyncio.run, args=(coro,), daemon=True).start()`. Substitui `asyncio.get_running_loop().create_task(...)`, que falhava silenciosamente porque agno chama tools sync em thread executor sem event loop ativo.
- `tools/provision.py` — `PlatformManifest` usa `metadata: MetadataSpec` (padrão Kubernetes), não `name` top-level. YAMLs em `wasp-gitops/infrastructure/tenants/` corrigidos no mesmo padrão.
- `tools/watcher.py` — 404 do k8s API agora é retry (ArgoCD demora a sincronizar). Só notifica em timeout final.
- `tools/watcher.py` — wrapper `watch_platform` com `try/except Exception: log.exception(...)` (fire-and-forget em thread daemon engole exceções).
- `tests/test_provision.py` e `tests/test_watcher.py` — atualizados para a nova arquitetura (mock de `threading.Thread`, novos cenários de 404).
- `CLAUDE.md` §13 — atualizado com aprendizados pós-smoke.

## What Worked

- `threading.Thread(target=asyncio.run, args=(coro,), daemon=True)` para spawnar work async de dentro de uma tool agno síncrona — cria event loop próprio na thread daemon.
- Tratar 404 como "ainda não criado" (sleep+retry) em vez de fatal: ArgoCD leva alguns segundos para sincronizar após o commit.
- Wrapper `_watch_platform_inner` + `try/except` no `watch_platform` público: garante que falhas em thread daemon apareçam nos logs.
- Logging explícito (`log.info("Watcher started"`, `log.info("Platform Ready — notifying")`) — única forma viável de debugar fire-and-forget threads.
- Mock de `threading.Thread` nos testes (`patch("tools.provision.threading.Thread", mock_thread_cls)`) — permite asserir spawn sem executar a coroutine.

## What Didn't Work

- `asyncio.get_running_loop().create_task(...)` em tool agno sync — agno chama via `run_in_executor` (sem loop ativo). Captura silenciosa em `except RuntimeError: pass` mascarava o problema. Watcher nunca executava.
- `asyncio.get_event_loop()` como fallback — Python 3.14 levanta `RuntimeError` se não houver loop. Mesma falha.
- Notificar erro "Platform não encontrada" no primeiro 404 — usuário viu mensagem de erro segundos depois do commit, antes do ArgoCD sincronizar. Deve apenas retry.
- Edits em arquivos durante `uvicorn --reload` (dev): `watchfiles` reinicia o processo e mata watchers em voo. Dev-only — em produção sem `--reload` não acontece.

## Next Steps

1. **Commit dos fixes pós-smoke** (5 arquivos modificados em `dev`). Mensagem sugerida: `fix(provision,watcher): spawn via thread, retry 404, log exceptions`.
2. **Limpar tenants de teste no `wasp-gitops`** — deletar `infrastructure/tenants/{sandbox-1..5,producao}.yaml` na branch `dev`. Manter apenas o tenant `example` se ainda for útil para Crossplane.
3. **Reforçar system prompt em `main.py`** — bot ainda emite "Pronto!", "Perfeito!" e menciona "ArgoCD" nas respostas, violando CLAUDE.md §11 (não vazar nomes internos) e §12 (tom — sem palavras de preenchimento). Adicionar exemplos negativos explícitos.
4. **Merge `dev` → `main`** após os itens acima.

### Backlog (depois)
- **Restart resilience do watcher** — persistir `platform_watches` em SQLite. Spec: `docs/specs/2026-05-16-platform-watcher-restart-resilience.md`.
- **Logging estruturado** — JSONL opcional via `LOG_FILE`. Spec: `docs/specs/2026-05-16-structured-logging.md`.
- **Status check manual** — tool para perguntar estado de uma Platform sem depender do watcher.
- **Operações além de criar** — update, delete, list de tenants.

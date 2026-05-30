# Handoff

## Why

Reorganizar `wasp/auth.py` (310 linhas, 4 responsabilidades misturadas) em pacote `wasp/auth/` com Repository Protocol + implementação SQLite + shims funcionais. Motivação registrada pelo usuário: migração futura para Postgres em ambientes gerenciados de cloud. Repository com Protocol passa a ter propósito real, não cargo cult de Java.

Alternativas rejeitadas:

- Splits granulares (`UsersRepository` + `InvitesRepository`) — deixaria órfãs as operações transacionais cross-table (`redeem_invite`, `bootstrap_admin`).
- Funções de módulo agrupadas por arquivo sem Protocol — não prepara para segundo backend.
- Apenas extrair `_db.py` interno — não resolve organização a médio prazo.

Spec aprovado: `docs/sdlc/02-design/2026-05-30-auth-repository.md`.

## In Progress

Refactor implementado e validado. Working tree tem alterações não-commitadas, aguardando `/commit`:

- Pacote `wasp/auth/` criado (`__init__.py`, `protocol.py`, `sqlite_repository.py`, `_schema.py`, `_connection.py`).
- `wasp/auth.py` deletado.
- `tests/conftest.py` modificado (sys.modules + `_reset_repository()`).
- `tests/test_auth_repository.py` criado.
- `CLAUDE.md` (raiz): nova seção "Repository pattern via Protocol", título da seção SQLite ajustado.
- `tests/CLAUDE.md`: notas sobre sys.modules.pop em pacotes + singleton + monkeypatch via shim.
- `docs/sdlc/02-design/2026-05-30-auth-repository.md` criado.

Próximo passo: rodar `make e2e-with-debug` antes do merge para `main` (CLAUDE.md exige).

## Open Questions / Hypotheses

- `WASP_AGENT_DB_BACKEND` documentado no spec mas ainda não adicionado a `docs/runbooks/auth-admin.md`.

## Known Broken

Nada. `make format`, `ruff check`, `make test` passam (317 passed, 1 skipped, 100% coverage). `make e2e-with-debug` **não foi executado** — *intentional*, agente não rodou por ser caro; rodar localmente antes de mergear.

## How to Resume

```bash
cd /home/silvios/git/wasp-agent && git status && ls wasp/auth/
```

Esperado: arquivos modificados + pacote `wasp/auth/` com 5 arquivos.

## Next Steps

1. Adicionar `WASP_AGENT_DB_BACKEND` em `docs/runbooks/auth-admin.md`.
2. Atualizar Status do spec `2026-05-30-auth-repository.md` para `Implemented` após merge.

### Decisão fechada nesta sessão

Desvio `_repo(None)` cria instância descartável em vez de usar singleton — **mantido**. Tentativa de mudar para singleton estrito (opção B) colide com `sys.modules.pop("wasp.auth")` no `mock_agno`: testes como `test_auth_guard.py` resolvem `monkeypatch.setattr("wasp.auth.is_authorized", ...)` pelo módulo, e remover o pop quebra esses testes. Custo da decisão: uma chamada `init_schema` idempotente extra por shim invocation. `get_repository()` permanece disponível para callers que migrarão deliberadamente quando Postgres entrar.

## Backlog (carry-over)

- **Discord slash commands** (`docs/sdlc/01-exploration/2026-05-27-discord-slash-commands.md`) — `/provision`, `/list`, `/status` como alternativa à linguagem natural
- **Handler de convite via DM no Discord** — hoje novos usuários Discord exigem `make admin-link` pelo operador; implementar redeem de token por DM elimina essa fricção (ver `wasp/clients/telegram/webhook.py` como referência)
- **Restart resilience do watcher** (`docs/sdlc/02-design/2026-05-16-platform-watcher-restart-resilience.md`) — persistir `platform_watches` em SQLite; restart do servidor cancela watchers em curso
- **Próximo CRD: `Cluster`** — seguir padrão: `wasp/resources/cluster/{manifest,provisioner,inventory}.py` + `@tool` em `wasp/provision.py`
- **Mover `extract_channel`/`extract_chat_id` para módulo folha** — hoje vivem em `watcher.py` mas são importados por `resources/platform/`; quando um terceiro CRD chegar, mover para ex: `wasp/session.py`
- **Status check manual** — tool para consultar estado de uma Platform sem depender do watcher
- **Operações além de criar** — update, delete, status individual de tenant
- **Authorization granular (RBAC)** — papéis (admin, operator, viewer)
- **Testcontainers** — avaliar substituir setup manual de k3d/Gitea nos E2E por `testcontainers-python`
- **Falha clara em configuração ausente** — validar variáveis obrigatórias no startup
- **PostgresAuthRepository** — implementar `wasp/auth/postgres_repository.py` quando migração for priorizada (Protocol já está pronto)
- **`waspctl good-citizen`** — `docs/sdlc/02-design/2026-05-30-good-citizen-test.md` precisa de plano de execução

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.

# Auth Singleton Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar todos os callers de produção e testes de `wasp.auth.<shim>(...)` para `wasp.auth.get_repository().<method>(...)`, depois remover os 10 shims funcionais de `wasp/auth/__init__.py`.

**Architecture:** Cada subsistema (main, guard, webhook, bot, cli) é migrado em conjunto com seus testes — produção e testes precisam mudar em lockstep porque os shims permanecem operacionais até a Task final. Os monkeypatches em testes passam de `monkeypatch.setattr("wasp.auth.is_authorized", ...)` para `monkeypatch.setattr(auth.get_repository(), "is_authorized", ...)`. O singleton é resetado entre testes pelo `mock_agno` (já presente em `tests/conftest.py`). Após todas as migrações, os shims e o teste `tests/test_auth.py` (duplicado com `tests/test_auth_repository.py`) são deletados.

**Tech Stack:** Python 3.14, pytest, `wasp/auth/` package (Protocol + SqliteAuthRepository), `superpowers:executing-plans` para execução.

**Spec source:** `docs/sdlc/02-design/2026-05-30-auth-singleton-migration.md`

---

### Task 1: Migrar `main.py` para `get_repository().init_schema()`

**Files:**
- Modify: `main.py:22`
- Modify: `tests/test_main.py:39-46`

- [ ] **Step 1: Atualizar o teste para patchar `init_schema` na instância**

Substituir o teste em `tests/test_main.py:39-46`:

```python
def test_main_initializes_auth_db(mock_agno, monkeypatch):
    init_called = []
    from wasp import auth

    repo = auth.get_repository()
    monkeypatch.setattr(repo, "init_schema", lambda: init_called.append(None))
    import main  # noqa: F401

    assert init_called
```

- [ ] **Step 2: Rodar o teste — deve FALHAR**

Run: `uv run pytest tests/test_main.py::test_main_initializes_auth_db -v`
Expected: FAIL (`assert init_called` falha — `main.py` ainda chama `auth.init_db()`, que reconstrói uma `SqliteAuthRepository` descartável fora do singleton patcheado).

- [ ] **Step 3: Atualizar `main.py:22`**

Trocar `main.py:21-24`:

```python
def create_app():
    auth.get_repository().init_schema()
    agent = build_agent()
    return ChannelLoader(agent).build_app()
```

- [ ] **Step 4: Rodar o teste — deve PASSAR**

Run: `uv run pytest tests/test_main.py::test_main_initializes_auth_db -v`
Expected: PASS.

- [ ] **Step 5: Rodar a suíte completa de `test_main.py`**

Run: `uv run pytest tests/test_main.py -v`
Expected: todos PASS (8 testes).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check .
git add main.py tests/test_main.py
git commit -m "refactor(auth): migrate main.py init_db to get_repository().init_schema()"
```

---

### Task 2: Migrar `auth_guard.py` + `test_auth_guard.py` + `test_provision.py` para `get_repository().is_authorized()`

**Files:**
- Modify: `wasp/auth_guard.py:25`
- Modify: `tests/test_auth_guard.py:27-76` (3 testes)
- Modify: `tests/test_provision.py` (8 monkeypatches nas linhas 92-93, 125-126, 314-315, 333-334, 354-357, 384-385, 419-420, 449-450, 489-490, 608-609)

- [ ] **Step 1: Atualizar `tests/test_auth_guard.py` — patchar instância**

Substituir os 3 testes que usam `monkeypatch.setattr("wasp.auth.is_authorized", ...)`:

```python
def test_guard_authorizes_known_tg_user(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard
    from wasp import auth

    monkeypatch.setattr(auth.get_repository(), "is_authorized", lambda c, i: "user-abc")
    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel="tg", chat_id="111", span=span)

    assert user_id == "user-abc"
    assert err is None
    span.set_attribute.assert_any_call("auth.channel", "tg")
    span.set_attribute.assert_any_call("user.id", "user-abc")


def test_guard_denies_unknown_tg_user(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard
    import wasp.telemetry as telemetry
    from wasp import auth

    monkeypatch.setattr(auth.get_repository(), "is_authorized", lambda c, i: None)
    auth_denied_calls = []
    monkeypatch.setattr(
        telemetry, "auth_denied", lambda **kw: auth_denied_calls.append(kw)
    )

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel="tg", chat_id="999", span=span)

    assert user_id is None
    assert err == {"status": "unauthorized", "message": "Acesso negado."}
    assert auth_denied_calls == [{"channel": "tg", "reason": "unknown_identity"}]
    span.set_attribute.assert_any_call("auth.channel", "tg")


def test_guard_denies_when_chat_id_missing(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard
    import wasp.telemetry as telemetry
    from wasp import auth

    called = []
    monkeypatch.setattr(
        auth.get_repository(),
        "is_authorized",
        lambda c, i: called.append((c, i)) or "user-abc",
    )
    monkeypatch.setattr(telemetry, "auth_denied", lambda **kw: None)

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel="tg", chat_id=None, span=span)

    assert user_id is None
    assert err == {"status": "unauthorized", "message": "Acesso negado."}
    assert called == []
```

- [ ] **Step 2: Atualizar `tests/test_provision.py` — patchar instância em todos os 10 call sites**

Para cada uma das 10 ocorrências de `monkeypatch.setattr("wasp.auth.is_authorized", <lambda>)` em `tests/test_provision.py`, trocar pelo padrão:

```python
from wasp import auth
monkeypatch.setattr(auth.get_repository(), "is_authorized", <lambda>)
```

Localizações (linhas referem-se ao arquivo atual antes da edição):

- Linha 92-94 (test #1): `lambda channel, channel_id: "user-abc"`
- Linha 125-127 (test #2): `lambda channel, channel_id: "user-abc"`
- Linha 314-316 (test #3): `lambda channel, channel_id: "user-abc"`
- Linha 333-334 (test #4): `lambda channel, channel_id: None`
- Linha 354-357 (test #5): `lambda c, i: is_authorized_called.append((c, i)) or None`
- Linha 384-386 (test #6): `lambda channel, channel_id: "user-abc"`
- Linha 419-420 (test #7): `lambda c, i: None`
- Linha 449-450 (test #8): `lambda c, i: "user-abc"`
- Linha 489-490 (test #9): `lambda c, i: None`
- Linha 608-610 (test #10): `lambda channel, channel_id: "user-abc"`

Exemplo de transformação (linha 92-94):

```python
# antes
monkeypatch.setattr(
    "wasp.auth.is_authorized", lambda channel, channel_id: "user-abc"
)

# depois
from wasp import auth as _auth
monkeypatch.setattr(
    _auth.get_repository(), "is_authorized", lambda channel, channel_id: "user-abc"
)
```

Importante: usar `_auth` como alias local para não conflitar caso o arquivo já tenha outros símbolos chamados `auth`. Alternativamente, importar `auth` no topo do módulo de teste uma única vez e referenciar `auth.get_repository()` em cada caso.

- [ ] **Step 3: Rodar testes — devem FALHAR (3 em test_auth_guard, 10 em test_provision)**

Run: `uv run pytest tests/test_auth_guard.py tests/test_provision.py -v`
Expected: 13 FAIL (`auth_guard.py` ainda chama `auth.is_authorized` direto — o patch na instância não atinge esse call site).

- [ ] **Step 4: Atualizar `wasp/auth_guard.py:25`**

Trocar linha 25:

```python
        user_id = auth.get_repository().is_authorized(channel, chat_id) if chat_id else None
```

- [ ] **Step 5: Rodar testes novamente — devem PASSAR**

Run: `uv run pytest tests/test_auth_guard.py tests/test_provision.py -v`
Expected: todos PASS.

- [ ] **Step 6: Rodar suíte completa para checar regressões cruzadas**

Run: `uv run pytest --no-cov -x`
Expected: todos PASS exceto `tests/test_auth_cli.py` (será migrada na Task 5) — que **deve** continuar passando porque os shims ainda existem.

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check .
git add wasp/auth_guard.py tests/test_auth_guard.py tests/test_provision.py
git commit -m "refactor(auth): route AuthorizationGuard through get_repository()"
```

---

### Task 3: Migrar `wasp/clients/discord/bot.py` para `get_repository().is_authorized()`

**Files:**
- Modify: `wasp/clients/discord/bot.py:32`

Não há monkeypatch direto em testes contra esse call site — `tests/test_discord.py` (se existir) não cobre o `on_message`; a auth dentro do `DiscordBot` só é exercitada em E2E. Migração mecânica.

- [ ] **Step 1: Atualizar `wasp/clients/discord/bot.py:32`**

Trocar linha 32:

```python
        if auth.get_repository().is_authorized("dc", user_id) is None:
```

- [ ] **Step 2: Rodar a suíte completa (sem e2e)**

Run: `uv run pytest --no-cov -x`
Expected: todos PASS (exceto `test_auth_cli.py` se ainda não migrado — não bloqueia esta task).

- [ ] **Step 3: Lint + commit**

```bash
uv run ruff check .
git add wasp/clients/discord/bot.py
git commit -m "refactor(auth): route Discord bot through get_repository()"
```

---

### Task 4: Migrar `wasp/clients/telegram/webhook.py` para `get_repository().redeem_invite` via lambda lazy

**Files:**
- Modify: `wasp/clients/telegram/webhook.py:70-72`

Razão para `lambda` em vez de bound method: o `mock_agno` reseta o singleton entre testes via `_reset_repository()`. Se passássemos `auth.get_repository().redeem_invite` (bound method capturado no momento de `_install_start_token_handler`), o callback ficaria ligado à instância antiga. A lambda resolve `get_repository()` na hora da chamada.

- [ ] **Step 1: Atualizar `wasp/clients/telegram/webhook.py:70-72`**

Trocar linhas 70-72:

```python
            handled = await _process_start_token(
                body, lambda *a: auth.get_repository().redeem_invite(*a), notifier.send
            )
```

- [ ] **Step 2: Rodar a suíte completa**

Run: `uv run pytest --no-cov -x`
Expected: todos PASS (`test_auth_cli.py` pode ainda usar shim — segue OK).

- [ ] **Step 3: Lint + commit**

```bash
uv run ruff check .
git add wasp/clients/telegram/webhook.py
git commit -m "refactor(auth): wrap redeem_invite in lazy lambda via get_repository()"
```

---

### Task 5: Migrar `wasp/auth_cli.py` + `tests/test_auth_cli.py` para `get_repository()`

**Files:**
- Modify: `wasp/auth_cli.py:51-94`
- Modify: `tests/test_auth_cli.py` (verificações em linhas 17, 29, 30, 42, 47, 63, 91, 96, 105 + setup em 77 e 104)

- [ ] **Step 1: Atualizar `tests/test_auth_cli.py` — usar `get_repository()` nas verificações**

Substituir todas as chamadas `auth.<method>(...)` por `auth.get_repository().<method>(...)`. Especificamente:

```python
# Verificações de redeem_invite — linhas 17, 29, 30, 42, 105
result = auth.get_repository().redeem_invite(out, "tg", "111")
...
assert auth.get_repository().redeem_invite(token, "local", "1") is None
assert auth.get_repository().redeem_invite(token, "tg", "222") is not None
...
auth.get_repository().redeem_invite(token, "tg", "333")
...
auth.get_repository().redeem_invite(token, "tg", "444")

# Verificações de is_authorized — linhas 47, 63, 91
assert auth.get_repository().is_authorized("tg", "333") is None
...
assert auth.get_repository().is_authorized("tg", "12345678") == user_id
...
assert auth.get_repository().is_authorized("dc", "708384119989600337") == user_id

# Setup helpers — linhas 41, 67, 77, 96, 104
token = auth.get_repository().create_invite(display_name="Carol", created_by="admin")
...
auth.get_repository().create_user("First")
...
user_id = auth.get_repository().create_user("Silvio")
...
auth.get_repository().link_identity(user_id, "dc", "111")
...
token = auth.get_repository().create_invite(display_name="Dave", created_by="admin")
```

- [ ] **Step 2: Rodar `test_auth_cli.py` — deve PASSAR**

Run: `uv run pytest tests/test_auth_cli.py -v`
Expected: todos PASS (shims ainda existem; `get_repository()` retorna instância que opera no mesmo `WASP_AGENT_DB_FILE` setado pela fixture autouse — `auth_cli` interno também usa `get_repository()` após Step 3, mas mesmo antes funciona porque shims e singleton apontam para o mesmo arquivo).

> ⚠️ Antes de Step 3, há descasamento de instância: `test_auth_cli` chama `auth.get_repository()` (cria instância A), `auth_cli.main` chama `auth.create_invite()` → shim cria instância B. Como ambas A e B leem `WASP_AGENT_DB_FILE` do mesmo `tmp_path`, os dados são compartilhados via SQLite. Os testes passam porque a fonte de verdade é o arquivo, não a instância. Step 3 elimina o descasamento.

- [ ] **Step 3: Atualizar `wasp/auth_cli.py:51-94`**

Adicionar `repo = auth.get_repository()` após `parse_args` e trocar todas as chamadas:

```python
    args = parser.parse_args(argv)
    repo = auth.get_repository()

    if args.cmd == "bootstrap":
        try:
            user_id = repo.bootstrap_admin(args.name, args.channel, args.channel_id)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1
        print(user_id)
        return 0

    if args.cmd == "link":
        try:
            repo.link_identity(args.user_id, args.channel, args.channel_id)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 1
        print("linked")
        return 0

    if args.cmd == "invite":
        token = repo.create_invite(
            display_name=args.name,
            created_by=args.created_by,
            channel=args.channel,
        )
        print(token)
        return 0

    if args.cmd == "revoke":
        ok = repo.revoke(args.channel, args.channel_id)
        if ok:
            print("revoked")
            return 0
        print("not found", file=sys.stderr)
        return 1

    # args.cmd == "list"
    rows = repo.list_identities()
    if not rows:
        print("(no identities)")
        return 0
    _print_table(rows)
    return 0
```

- [ ] **Step 4: Rodar `test_auth_cli.py` novamente**

Run: `uv run pytest tests/test_auth_cli.py -v`
Expected: todos PASS (agora ambos os lados usam o singleton).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check .
git add wasp/auth_cli.py tests/test_auth_cli.py
git commit -m "refactor(auth): route auth_cli through get_repository()"
```

---

### Task 6: Migrar `tests/e2e/conftest.py` para patchar a instância

**Files:**
- Modify: `tests/e2e/conftest.py:226-241`

- [ ] **Step 1: Atualizar `tests/e2e/conftest.py:239-241`**

Trocar:

```python
    monkeypatch.setattr(
        wasp.auth.get_repository(), "is_authorized", lambda channel, channel_id: "e2e-user"
    )
```

(o `import wasp.auth` na linha 228 e o `wasp.auth.get_repository()` resolvem corretamente — `wasp/auth/__init__.py` ainda exporta `get_repository`.)

- [ ] **Step 2: Rodar smoke e2e (rápido)**

Run: `uv run pytest tests/e2e/ -m e2e --no-cov -x -k "smoke or basic" --co`
Expected: collect bem-sucedido (sem erro de import). Execução real fica para Task 10.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/conftest.py
git commit -m "refactor(auth): patch get_repository() instance in e2e conftest"
```

---

### Task 7: Confirmar paridade `tests/test_auth.py` ↔ `tests/test_auth_repository.py`; migrar lacunas

**Files:**
- Read: `tests/test_auth.py`
- Read: `tests/test_auth_repository.py`
- Modify: `tests/test_auth_repository.py` (somente se houver gap)

- [ ] **Step 1: Listar testes de cada arquivo**

Run: `uv run pytest tests/test_auth.py --collect-only -q`
Run: `uv run pytest tests/test_auth_repository.py --collect-only -q`

- [ ] **Step 2: Comparar a lista**

Identificar testes cuja semântica está em `test_auth.py` mas NÃO em `test_auth_repository.py`. Comparação esperada (baseada na leitura inicial):

`test_auth.py` cobre:
- `test_init_db_creates_three_tables` ↔ `test_init_schema_creates_three_tables` ✅
- `test_init_db_is_idempotent` ↔ `test_init_schema_is_idempotent` ✅
- `test_is_authorized_returns_none_for_unknown` ↔ idem ✅
- `test_create_user_returns_uuid_and_persists` — verificação direta no SQLite com `auth_users.display_name`. `test_auth_repository::test_create_user_and_link_identity` cobre apenas via API. **Gap possível.**
- `test_link_identity_allows_is_authorized` ↔ `test_create_user_and_link_identity` ✅
- `test_create_invite_returns_urlsafe_token` ↔ idem ✅
- `test_create_invite_persists_with_expires_at_from_default_ttl` — verifica TTL padrão (1h) sem env var. **Gap: `test_auth_repository` só tem `test_create_invite_uses_env_ttl`.**
- `test_create_invite_uses_env_ttl` ↔ idem ✅
- `test_redeem_invite_creates_identity_and_returns_user` ↔ idem ✅
- `test_redeem_invite_returns_none_for_unknown_token` ↔ idem ✅
- `test_redeem_invite_returns_none_when_expired` ↔ idem ✅
- `test_redeem_invite_returns_none_when_already_consumed` ↔ idem ✅
- `test_redeem_invite_rejects_channel_mismatch` ↔ idem ✅
- `test_revoke_removes_identity_keeps_user` ↔ idem ✅
- `test_revoke_returns_false_when_not_found` ↔ idem ✅
- `test_list_identities_returns_dicts` ↔ idem ✅
- `test_has_any_user_false_then_true` ↔ idem ✅
- `test_db_file_defaults_to_env_var` ↔ idem ✅
- `test_init_db_without_args_uses_env_var` — testa que `auth.init_db()` sem args usa env var. **Gap: equivalente faltando — adicionar via `SqliteAuthRepository().init_schema()`.**
- `test_bootstrap_creates_first_user_when_db_empty` ↔ idem ✅
- `test_bootstrap_fails_when_db_not_empty` ↔ idem ✅
- `test_redeem_invite_concurrent_unbound_token_only_succeeds_once` ↔ idem ✅
- `test_redeem_invite_rejects_when_identity_already_linked` ↔ idem ✅

Confirmar essa análise lendo ambos os arquivos e ajustando se necessário.

- [ ] **Step 3: Adicionar testes faltantes em `tests/test_auth_repository.py`**

Para os 3 gaps identificados (`test_create_user_returns_uuid_and_persists`, `test_create_invite_persists_with_expires_at_from_default_ttl`, `test_init_db_without_args_uses_env_var`), adicionar versões via Repository:

```python
def test_create_user_persists_display_name_in_sqlite(repo):
    user_id = repo.create_user("Alice")
    con = sqlite3.connect(repo._db_file)
    try:
        row = con.execute(
            "SELECT display_name FROM auth_users WHERE user_id=?", (user_id,)
        ).fetchone()
        assert row is not None
        assert row[0] == "Alice"
    finally:
        con.close()


def test_create_invite_default_ttl_is_one_hour(repo, monkeypatch):
    monkeypatch.delenv("WASP_AGENT_INVITE_TTL_HOURS", raising=False)
    admin = repo.create_user("Admin")
    token = repo.create_invite("Bob", created_by=admin)
    con = sqlite3.connect(repo._db_file)
    try:
        row = con.execute(
            "SELECT created_at, expires_at FROM auth_invites WHERE token=?",
            (token,),
        ).fetchone()
    finally:
        con.close()
    created = datetime.fromisoformat(row[0])
    expires = datetime.fromisoformat(row[1])
    assert expires - created == timedelta(hours=1)


def test_init_schema_no_args_uses_env_var(tmp_path, monkeypatch):
    target = str(tmp_path / "init_env.db")
    monkeypatch.setenv("WASP_AGENT_DB_FILE", target)
    SqliteAuthRepository().init_schema()
    con = sqlite3.connect(target)
    try:
        names = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        con.close()
    assert "auth_users" in names
    assert "auth_identities" in names
    assert "auth_invites" in names
```

> Se a análise do Step 2 identificar zero gaps reais (porque já existe cobertura equivalente que esta lista perdeu), pular Step 3 e justificar no commit.

- [ ] **Step 4: Rodar `test_auth_repository.py` com coverage**

Run: `uv run pytest tests/test_auth_repository.py -v --cov=wasp.auth --cov-report=term-missing`
Expected: todos PASS, coverage `wasp/auth/` em 100%.

- [ ] **Step 5: Commit (se houve mudança)**

```bash
git add tests/test_auth_repository.py
git commit -m "test(auth): backfill repository coverage from legacy test_auth.py"
```

---

### Task 8: Deletar `tests/test_auth.py`

**Files:**
- Delete: `tests/test_auth.py`

- [ ] **Step 1: Deletar arquivo**

Run: `git rm tests/test_auth.py`

- [ ] **Step 2: Rodar suíte completa com coverage**

Run: `uv run pytest --cov=wasp --cov-report=term-missing`
Expected: todos PASS, coverage em 100% para `wasp/auth/`.

> Se coverage cair abaixo de 100% no pacote `wasp/auth/`, identificar branch descoberto e voltar à Task 7 Step 3 para adicionar o teste equivalente em `test_auth_repository.py` antes de prosseguir.

- [ ] **Step 3: Commit**

```bash
git commit -m "test(auth): remove duplicate test_auth.py (covered by test_auth_repository.py)"
```

---

### Task 9: Remover shims de `wasp/auth/__init__.py` + limpar teste obsoleto + atualizar `tests/CLAUDE.md`

**Files:**
- Modify: `wasp/auth/__init__.py` (deletar `_repo`, 10 shims; reduzir `__all__`)
- Modify: `tests/test_auth_repository.py` (remover `test_shim_resolves_env_per_call`)
- Modify: `tests/CLAUDE.md` (remover orientação obsoleta sobre patchar o shim)

- [ ] **Step 1: Substituir `wasp/auth/__init__.py` pelo conteúdo final**

Conteúdo completo do arquivo:

```python
import os

from wasp.auth.protocol import AuthRepository as AuthRepository
from wasp.auth.sqlite_repository import SqliteAuthRepository as SqliteAuthRepository

__all__ = ["AuthRepository", "SqliteAuthRepository", "get_repository"]

_repository: AuthRepository | None = None


def get_repository() -> AuthRepository:
    global _repository
    if _repository is None:
        backend = os.getenv("WASP_AGENT_DB_BACKEND", "sqlite")
        if backend == "sqlite":
            _repository = SqliteAuthRepository()
        else:
            raise ValueError(f"unsupported backend: {backend}")
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None
```

- [ ] **Step 2: Remover `test_shim_resolves_env_per_call` de `tests/test_auth_repository.py`**

Excluir o bloco inteiro do teste (linhas 237-245 — começa em `def test_shim_resolves_env_per_call(monkeypatch, tmp_path):` e termina antes do EOF). Os testes `test_get_repository_returns_singleton` e `test_get_repository_unsupported_backend_raises` permanecem.

- [ ] **Step 3: Atualizar `tests/CLAUDE.md` — remover orientação obsoleta**

No arquivo `tests/CLAUDE.md`, localizar o parágrafo:

> Cuidado ao remover `wasp.auth` do `sys.modules.pop`: testes como `test_auth_guard.py` e `test_provision.py` fazem `monkeypatch.setattr("wasp.auth.is_authorized", ...)`, que pytest resolve via `getattr(wasp, "auth")`...

Substituir por:

> Testes que precisam mockar auth devem fazer `monkeypatch.setattr(auth.get_repository(), "is_authorized", ...)` — patchando a instância singleton em vez do nome no módulo. O `mock_agno` chama `_reset_repository()` no setup e teardown, garantindo que cada teste começa com singleton limpo e que o patch atinge a instância usada pelo caller.

E na seção "E2E fixture — patch `_select_notifier`, not `TelegramNotifier`", localizar:

> Also monkeypatch `wasp.auth.is_authorized` to return a fake `user_id` — without it the auth guard silently returns `{"status": "unauthorized"}` and the test fails downstream at Gitea's `get_file()` with 404. O shim funcional em `wasp/auth/__init__.py` preserva esse monkeypatch — patcheie no shim, não em `SqliteAuthRepository`.

Substituir por:

> Also monkeypatch `wasp.auth.get_repository().is_authorized` to return a fake `user_id` — without it the auth guard silently returns `{"status": "unauthorized"}` and the test fails downstream at Gitea's `get_file()` with 404. Patcheie a instância do singleton, não o `SqliteAuthRepository` diretamente.

- [ ] **Step 4: Rodar suíte completa com coverage**

Run: `uv run pytest --cov=wasp --cov-report=term-missing`
Expected: todos PASS, coverage 100%.

- [ ] **Step 5: Lint**

Run: `uv run ruff check .`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add wasp/auth/__init__.py tests/test_auth_repository.py tests/CLAUDE.md
git commit -m "refactor(auth): remove functional shims; get_repository() is the sole entrypoint"
```

---

### Task 10: Validação final (`make format`, `make test`, `make e2e-with-debug`) + atualizar Status do spec

**Files:**
- Modify: `docs/sdlc/02-design/2026-05-30-auth-singleton-migration.md` (Status: Draft → Implemented)
- Modify: `HANDOFF.md` (remover item "In Progress" e "Next Steps" relativos a esta migração)

- [ ] **Step 1: Rodar formatação**

Run: `make format`
Expected: nenhuma mudança (já lintado em cada task).

- [ ] **Step 2: Rodar testes unitários completos**

Run: `make test`
Expected: todos PASS, coverage 100%.

- [ ] **Step 3: Rodar E2E**

Run: `make e2e-with-debug`
Expected: PASS. O e2e exercita o ciclo completo: agno carrega `main.py` → `auth.get_repository().init_schema()` → watcher chama `AuthorizationGuard.check` → `auth.get_repository().is_authorized` (patcheado pelo `tests/e2e/conftest.py` para retornar `"e2e-user"`) → fluxo segue.

> Se o e2e falhar com auth-related error, verificar que `tests/e2e/conftest.py` está patchando a instância correta. O `mock_agno` **não** roda em e2e (marker `e2e` faz a fixture retornar cedo) — então `_reset_repository()` não é chamado. A instância singleton sobrevive entre testes e2e dentro da mesma sessão, mas o patch via `monkeypatch.setattr(wasp.auth.get_repository(), ...)` é desfeito pelo monkeypatch ao fim de cada teste.

- [ ] **Step 4: Atualizar Status do spec**

Editar `docs/sdlc/02-design/2026-05-30-auth-singleton-migration.md` linha 3:

```markdown
**Status:** Implemented  
```

- [ ] **Step 5: Atualizar `HANDOFF.md`**

Remover as seções "Why", "In Progress" e "Next Steps" que descrevem esta migração. Substituir por nova seção `## Why` enxuta apontando para o próximo item do Backlog (ou deixar `HANDOFF.md` vazio salvo Backlog).

- [ ] **Step 6: Commit final**

```bash
git add docs/sdlc/02-design/2026-05-30-auth-singleton-migration.md HANDOFF.md
git commit -m "docs(auth): mark singleton-migration spec as Implemented"
```

- [ ] **Step 7: Push (somente após autorização do usuário)**

Não fazer push automaticamente. Reportar conclusão e pedir confirmação.

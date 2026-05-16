# CLAUDE.md

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 5. TDD

We are passionate about testing. We write tests for every feature, bug fix, and refactor. Tests are the safety net that allows us to move fast without breaking things.

The code coverage threshold is 100%. Use `pytest --cov` (`pytest-cov` + `coverage.py`) to verify coverage.

## 6. Code

This project uses primarily Python. For formatting code, use `ruff`.

For dependencies we use `uv`.

## 7. Brainstorming and specification

Flow: brainstorm → spec → plan

All files stored in `docs/`, named `<YYYY-MM-DD>-<topic>.md`:
1. `brainstorms/` — session context, decisions, alternatives
2. `specs/` — approved design (what to build)
3. `plans/` — implementation plan (how to build, step-by-step)

## 8. agno

- Versão mínima: `agno>=2.0.0`. A API 1.x é diferente e incompatível.
- Sessão SQLite: `db=SqliteDb(db_file=..., session_table=...)` via `agno.db.sqlite.sqlite`. Não existe `SqliteAgentStorage`.
- Histórico de contexto: `add_history_to_context=True` (não `add_history_to_messages`).
- `SqliteDb` requer `sqlalchemy` — declare como dependência explícita no projeto.
- Antes de escrever código com agno, verifique os caminhos de import no pacote instalado (`.venv/lib/`). A documentação oficial frequentemente diverge da versão instalada.

- `@tool` sem `requires_confirmation`: o decorator agora é usado sem argumentos (`mocks["agno.tools"].tool = lambda fn: fn` no conftest). `requires_confirmation=True` é incompatível com Telegram — ver seção 11.

Para detalhes e checklist de ciclos futuros, ver `docs/notes/2026-05-13-agno-api-cycle1.md`.

Para rodar o bot localmente com ngrok, ver `docs/runbooks/telegram-local-dev.md`.

## 12. Telegram — tom do bot

No system prompt, incluir instruções explícitas de anti-padrões para controlar o tom do LLM:
- Sem palavras de preenchimento ("Certo!", "Perfeito!", "Excelente!")
- Sem emojis, sem exclamações
- Parágrafos curtos separados por linha em branco
- Evitar listas com bullet e bold salvo quando a estrutura genuinamente ajuda
- Ao repassar resultado de tool bem-sucedida, usar o campo `message` do dict — não inventar texto adicional

## 9. Security tracking

Issues de segurança ativas ficam em `docs/security/issues/SEC-NNN-<slug>.md`.
Quando resolvida, mover para `docs/security/issues/archived/`.

Cada arquivo tem: `id`, `severity`, `status`, `opened` (e `resolved` quando arquivada), descrição, impacto e fix.

Ao fazer security review, checar issues abertas antes de reportar duplicatas.

## 11. Platform provisioning

- GitOps repo: `smsilva/wasp-gitops`, branch `dev`, path `infrastructure/tenants/{name}.yaml`.
- CRD: `apiVersion: wasp.silvios.me/v1alpha1`, `kind: Platform`. Campo `name` é top-level (não em `metadata`).
- Endpoint derivado deterministicamente: `gateway.{aws-region}.{name}.{domain}` — nenhum campo desconhecido no momento do commit.
- Services são fixos para toda instância: auth, discovery, callback, portal.
- Default domain: `wasp.silvios.me`. Default region: `us-east-1`.
- Use Pydantic models para gerar o manifesto (não Jinja2). O LLM extrai parâmetros; Pydantic valida e serializa. Nunca peça pro LLM gerar YAML Crossplane diretamente.
- Tools de provisionamento usam confirmação via LLM (system prompt) — `@tool(requires_confirmation=True)` é incompatível com a interface Telegram (não há handler para `RunPausedEvent`).
- Sempre usar `yaml.safe_dump()` (não `yaml.dump()`) ao serializar manifests — impede que input do LLM/usuário injete objetos Python arbitrários no YAML.
- Parâmetros `list` com default em tool functions: usar tupla como constante (`DEFAULT_REGIONS = ("us-east-1",)`) e `None` na assinatura com inicialização no corpo (`regions = list(DEFAULT_REGIONS)`). Lista mutável como default é Python gotcha.
- Sanitizar strings de usuário antes de interpolar em mensagens de commit: `value.replace("\n", " ").replace("\r", " ")` — evita injeção de linhas extras no commit message.
- Erros em tools de provisionamento devem retornar dict genérico `{"status": "error", "message": "..."}` — nunca `raise`, para não vazar detalhes internos ao usuário via LLM.
- O LLM surfacia **todos os campos** do dict retornado por uma tool. Incluir apenas campos com valor para o usuário final; excluir `commit_sha`, `file_path`, nomes internos de sistemas (ex: "ArgoCD").
- `GH_PAT`: fine-grained PAT no GitHub com escopo mínimo (`smsilva/wasp-gitops`, Contents: write). Ver `docs/runbooks/github-pat-setup.md`.

Para o design completo do ciclo 2, ver `docs/specs/2026-05-15-platform-provisioning-design.md`.

Para criar um cluster k3d com ArgoCD, Crossplane e a Application `wasp-gitops` sincronizando `infrastructure/tenants` do repo `smsilva/wasp-gitops` (branch `dev`), ver `docs/runbooks/k3d-argocd-wasp-gitops.md`. O manifesto da Application está em `manifests/argocd/wasp-gitops-application.yaml`. O script de criação do cluster está em `~/git/kubernetes/lab/argo/argocd/run` (repo `smsilva/kubernetes`) — o `run` orquestra em sequência: k3d-cluster-creation → argocd-install → argocd-notification → crossplane-install → argocd-get-initial-password.

- Crossplane: versão 2.2.1, namespace `crossplane-system`, script `crossplane-install.sh` no mesmo diretório do `run`.
- `smsilva/kubernetes` usa `main` como branch principal — sempre criar feature branch antes de commitar.
- Manifestos locais (XRD, Compositions, Functions, Providers, ProviderConfigs, Application ArgoCD, tenants de teste) ficam em `manifests/` no root do projeto — subpastas: `crossplane/xrd/`, `crossplane/compositions/`, `crossplane/functions/`, `crossplane/providers/`, `crossplane/providerconfigs/`, `argocd/`, `tenants/`.
- Crossplane Compositions para Platform usam `metadata.name` para derivar tanto o nome quanto o namespace dos recursos criados.
- Nomes de Compositions devem refletir o tipo do recurso composto (`platform`), não a implementação (`platform-configmap`).
- O provider `upbound/provider-kubernetes` com `ProviderConfig` usando `InjectedIdentity` é necessário para Compositions criarem objetos no cluster local k3d.
- XRD usa `apiextensions.crossplane.io/v2` com `spec.scope: Cluster`. O campo `scope` é imutável após criado — para alterar é necessário deletar e recriar a XRD (destrutivo para CRs existentes).
- Composition continua em `apiextensions.crossplane.io/v1` (não há v2). O modo `spec.resources` (patch-and-transform nativo) foi REMOVIDO no Crossplane v2 — usar `spec.mode: Pipeline` com `function-patch-and-transform`. Manifesto em `manifests/crossplane/functions/`.
- Quando a Composition cria recursos em um namespace dedicado, ela própria precisa criar o `Namespace` (provider-kubernetes não cria automaticamente). Adicionar o Namespace como recurso `Object` antes do ConfigMap (ou demais) na pipeline.
- `ProviderConfig` do provider-kubernetes com `InjectedIdentity` exige `ClusterRoleBinding` para o SA do provider em `crossplane-system`. O nome do SA é gerado em runtime (`provider-kubernetes-<hash>`) e muda em reinstalações — usar `DeploymentRuntimeConfig` para pinar o SA antes de bindings estáveis.
- Pinar o SA do provider: criar um `DeploymentRuntimeConfig` com `spec.serviceAccountTemplate.metadata.name: provider-kubernetes` e referenciá-lo no `Provider` via `spec.runtimeConfigRef.name`. O nome do Deployment continua tracking a revision (ex.: `provider-kubernetes-f8518c887488`), mas o `serviceAccountName` interno passa a ser o pinado e o `ClusterRoleBinding` fica estável entre reinstalações.
- Drift do provider-kubernetes não é detectado em tempo real: quando o objeto gerenciado é deletado externamente, o `Object` reporta `Ready=True` por alguns minutos até a próxima reconciliação periódica. Forçar reconciliação imediata: `kubectl annotate object <name> reconcile=$(date +%s) --overwrite`.

## 10. ruff / lint

- `# noqa: E402` nos imports após `load_dotenv()` em `main.py` — violação intencional (env vars devem estar carregadas antes dos imports do agno).
- `# noqa: F401` em `import main` dentro de funções de teste — import por efeito colateral (executa código de módulo).
- `ruff check .` deve passar limpo. Rode antes de qualquer commit.

## 13. Watcher assíncrono (Ciclo 3)

- `tools/watcher.py` — `watch_platform(name, chat_id, token)`: polling de Platform CR via `kubernetes.client.CustomObjectsApi`, 10s/poll, 10min timeout, notifica via `httpx.AsyncClient` POST direto na Telegram API.
- Spawn: em `provision_platform_instance`, após `repo.create_file` bem-sucedido: `asyncio.get_running_loop().create_task(watch_platform(...))`. Envolto em `try/except RuntimeError: pass` para contextos sem event loop.
- `run_context=None` em `provision_platform_instance` — agno injeta o contexto de execução; `extract_chat_id` faz parse de `session_id = "tg:{entity}:{chat_id}"`. Se não for sessão Telegram ou `TELEGRAM_TOKEN` não estiver setado, watcher não é spawnado silenciosamente.
- `RunContext` está em `agno.run.base` (agno 2.6.5).
- `pytest-asyncio` versão 1.3.0 usa strict mode por default — adicionar `asyncio_mode = "auto"` no `[tool.pytest.ini_options]` para evitar `@pytest.mark.asyncio` em cada teste.
- Mocks de `kubernetes` e `kubernetes.config` no conftest: `ConfigException` e `ApiException` são MagicMock — não podem ser usados em `raise`/`except`. Nos testes que precisam testar essas exceções, criar `FakeConfigException(Exception)` / `FakeApiException(Exception)` reais e fazer `monkeypatch.setattr(w.config, "ConfigException", FakeConfigException)` antes de usar.
- `monkeypatch.setattr("tools.provision.asyncio.get_running_loop", ...)` não funciona — `monkeypatch` com dotted string trata `tools.provision.asyncio` como módulo aninhado. Usar `monkeypatch.setattr(asyncio, "get_running_loop", ...)` (módulo real importado no teste).
- Ao mockar `time.monotonic` com `iter([...])` em testes async: o teardown do event loop chama `time.monotonic()` extras vezes, causando `StopIteration`. Usar `itertools.chain([...], repeat(ultimo_valor))` para never-exhausting iterator.
- Warning `coroutine 'watch_platform' was never awaited` em testes que mockam `loop.create_task`: inofensivo — o mock não executa a coroutine, que é coletada pelo GC. Não suprimir; é artefato esperado do mock setup.
- `notify_telegram` usa `httpx.AsyncClient` direto — não reusa o cliente do agno/Telegram (não há acesso). Overhead aceitável: uma conexão por notificação.

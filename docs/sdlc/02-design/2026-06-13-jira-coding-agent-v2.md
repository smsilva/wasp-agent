# Jira Coding Agent v2 — implementação real (claude-code-action + GitHub App oficial)

**Status:** Approved
**Data:** 2026-06-13
**Autor:** Silvio (brainstorming com Claude)
**Spec base (v1):** `docs/sdlc/02-design/2026-06-13-jira-coding-agent.md`

---

## 1. Contexto

A v1 (walking skeleton) provou o round-trip Jira → GitHub Actions → comentário no Jira,
com todos os passos do pipeline como stubs que só logam. A v2 substitui os stubs por
implementação real: o agente lê a issue, implementa a tarefa, abre um PR e devolve o
status ao Jira, transicionando a issue para "In Review".

Permanece **fora da v2** (fica em v3): gate de ambiguidade, `pr-agent.yaml` (auto-fix de
CI), `dry_run`, e extração da lógica para CLI Python testado.

---

## 2. Decisões de design (revisão sobre o spec base)

As decisões abaixo **revisam** o §5 e a tabela §3 do spec base. O racional de cada mudança
está na coluna "Razão".

| # | Tópico | Spec base (v1) | v2 (decidido) | Razão |
|---|---|---|---|---|
| 3 | Identidade no GitHub | GitHub App próprio + `create-github-app-token` | **App oficial da Anthropic ("Claude") via `claude-code-action`** | A app oficial já está instalada no repo. A action cunha um installation token internamente a partir do `CLAUDE_CODE_OAUTH_TOKEN` — não precisa de private key nem de PAT. Commits/PR saem como `claude[bot]` e, por serem token de App (≠ `GITHUB_TOKEN`), **disparam o `ci.yaml` no PR**. |
| 2 | Motor de coding | `claude -p` headless cru | **`anthropics/claude-code-action` em automation mode** | Menos cola: a action gerencia install, auth (OAuth token), token de App e operações de git/PR. Lê `CLAUDE.md` nativo. É a mesma action que a v3 (`pr-agent.yaml`) vai usar. |
| — | Auth do Claude | `ANTHROPIC_API_KEY` | **`CLAUDE_CODE_OAUTH_TOKEN`** (assinatura) | Sem cobrança por token de API; gerado via `claude setup-token`. |
| — | Conteúdo da issue | ADF → markdown | **`expand=renderedFields`** (HTML pronto do Jira) | Evita parser de ADF não-trivial em bash; mantém a v2 sem código Python novo. |

**Consequência:** a v2 **não** introduz `AGENT_GH_PAT`, nem `scripts/branch-name`, nem
scripts de commit/push/PR — o lado GitHub inteiro é delegado à action. O lado Jira
continua sendo nosso (a app não fala com Jira).

---

## 3. Arquitetura da v2

```
Jira: atribui/transiciona a issue
   └─ Automation → repository_dispatch (event_type: jira-trigger-event, client_payload.issue_key)
GitHub: jira-agent.yaml
   1. lê + valida issue_key (regex ^[A-Z]+-[0-9]+$)                         [real, já existe]
   2. scripts/jira-fetch "$ISSUE_KEY" → prompt (summary + description HTML)  [real, novo]
   3. anthropics/claude-code-action: implementa → branch → commit → PR      [real, App oficial]
   4. scripts/jira-comment: comenta no Jira com a URL do PR                  [real, já existe]
   5. scripts/jira-transition "$ISSUE_KEY" "In Review"                       [real, novo]
```

A action (passo 3) é a fronteira: tudo no lado GitHub (implementação, branch, commit, PR)
é dela. Os passos 2, 4 e 5 são o lado Jira, em bash testado.

---

## 4. Componentes

Convenção de bash do projeto (regras globais): sem extensão no executável, long-form CLI
options, 2-space indent, locais minúsculos, sempre aspas em `"${var}"`, args obrigatórios
via `${var?}`, `set -e` para sequência. Cada script novo é testado por pytest contra um
mock HTTP server local, no padrão de `tests/test_jira_comment.py`.

### 4.1 `scripts/jira-fetch` (novo)
- `GET ${JIRA_BASE_URL}/rest/api/3/issue/{key}?expand=renderedFields&fields=summary` (basic
  auth `JIRA_EMAIL:JIRA_API_TOKEN`).
- Emite em stdout um prompt em markdown: um preâmbulo de instrução fixo + o `summary` +
  o `renderedFields.description` (HTML). O workflow redireciona para um arquivo passado a
  `prompt_file` da action (ou usa `prompt` direto).
- Teste: valida método/endpoint/auth e que o output contém o summary e o corpo renderizado.

### 4.2 `scripts/jira-transition` (novo)
- `GET .../issue/{key}/transitions` → encontra a transição cujo `name` casa (case-insensitive)
  com o alvo ("In Review") → pega o `id`.
- `POST .../issue/{key}/transitions` com `{"transition": {"id": "<id>"}}`.
- Resolver por **nome**, não por id fixo: ids de transição são específicos do workflow da
  instância Jira.
- Falha com mensagem clara se o nome não existir nas transições disponíveis.
- Teste: mock server retorna lista de transições; valida o match e o POST com o id correto.

### 4.3 `scripts/jira-comment` (existe, reusado)
- Reusado para postar o comentário com a URL do PR. Sem mudança.

### 4.4 `.github/workflows/jira-agent.yaml` (modificado)
- Remove os stubs `Fetch issue`/`Create branch`/`Implement with claude`/`Commit and push`/`Open PR`.
- `Build prompt`: `scripts/jira-fetch "$ISSUE_KEY" > "$RUNNER_TEMP/prompt.md"`.
- `Implement`: `uses: anthropics/claude-code-action@v1` com:
  - `prompt_file: ${{ runner.temp }}/prompt.md`
  - `claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}`
  - `model: claude-opus-4-8`
  - permissões do job (`permissions:`) e flags exatas a fixar no plano (ver §6).
  - **O prompt deve instruir:** nome do branch e título do PR **contendo a issue key**
    (ex: `agent/PLTF-11-...` e título começando com `PLTF-11`). Isso é o que faz a app
    GitHub for Jira linkar o PR ao dev panel da issue (ver §10).
- `Comment + transition`: lê a URL do PR criado, chama `scripts/jira-comment` e
  `scripts/jira-transition`.
- Mantém a validação de `issue_key` por regex (input não-confiável do `client_payload`).

---

## 5. Secrets (v2)

Adiciona um único secret ao que a v1 já usa (`JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`):

| Secret | Uso |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Auth do Claude na action (gerado via `claude setup-token`) |

Não há secret de git: a app oficial fornece o token de operações de git/PR internamente.

---

## 6. Pontos a confirmar no plano de execução

1. **Abertura do PR em automation mode.** Confirmar que `claude-code-action` disparada por
   `repository_dispatch` **abre o PR** (não só pusha o branch). Se não for automático nesse
   modo, instruir explicitamente no prompt (a action tem tooling de git/PR embutido) ou
   permitir as tools necessárias.
2. **Como obter a URL do PR criado** para o passo de comentário no Jira (output da action,
   ou consulta via `gh pr list --head <branch>`).
3. **Bloco `permissions:` do job** exigido pela action (provável `contents: write`,
   `pull-requests: write`; `id-token: write` só se usar federation — não é o caso).
4. **Pin de versão** da action (`@v1` vs SHA) seguindo o padrão do repo.

---

## 7. Testes e validação

- `scripts/jira-fetch` e `scripts/jira-transition` cobertos por pytest (mock HTTP server).
  Sem código Python de produção novo → 100% coverage permanece intacto.
- `make test` e e2e seguem verdes (não tocam o workflow).
- **E2E real (manual):** disparar a issue de teste **PLTF-11** e conferir:
  1. run verde na aba Actions;
  2. branch criado e PR aberto como `claude[bot]` com diff real;
  3. `ci.yaml` rodando no PR do agente;
  4. comentário no Jira com a URL do PR;
  5. issue transicionada para "In Review".

---

## 8. Runbook

Reescrever `docs/runbooks/jira-coding-agent-setup.md` para refletir o setup v2 como o
caminho corrente (v1 vira nota histórica onde fizer sentido). Cobrir:

- **GitHub:** confirmar a app oficial "Claude" instalada no repo (`github.com/apps/claude`);
  adicionar o secret `CLAUDE_CODE_OAUTH_TOKEN` (como gerar via `claude setup-token`); manter
  os secrets Jira da v1.
- **Jira:** automation rule (inalterada da v1); garantir que a transição "In Review" existe
  no workflow do projeto PLTF; (opcional) confirmar a app GitHub for Jira instalada no site
  `smsilva.atlassian.net` para o dev panel (ver §10).
- **Validação:** os 5 pontos do §7.
- **Troubleshooting v2:** action sem permissão de PR; transição "In Review" inexistente;
  OAuth token expirado.

---

## 9. Critérios de sucesso da v2

- Disparar a issue dispara o `jira-agent.yaml`, que implementa, abre um PR como `claude[bot]`
  e o `ci.yaml` roda nesse PR.
- A issue do Jira recebe um comentário com a URL do PR e é transicionada para "In Review".
- Nenhum secret de git de longa duração no repositório (sem PAT; só o OAuth token do Claude).

---

## 10. Relação com a app GitHub for Jira

Avaliamos usar integrações oficiais da Atlassian para evitar os scripts Jira. Conclusão:
elas **complementam**, não substituem.

### 10.1 O que foi descartado
- **`atlassian/gajira-*`** (gajira-comment, gajira-transition): **deprecados e sem
  manutenção** (último release nov/2022, aviso explícito no repo). Usar action de terceiros
  abandonada que manuseia o token do Jira contraria a disciplina de supply chain do projeto.
  Descartado.

### 10.2 O que a app GitHub for Jira cobre (e o que não cobre)
A app oficial **GitHub for Atlassian** (by Atlassian, Cloud Fortified) sincroniza
branches/commits/PRs do GitHub para o **dev panel** da issue, quando a issue key aparece no
nome do branch / título do PR / mensagem de commit. É fluxo **GitHub → Jira**.

Mapeando nas três necessidades do lado Jira:

| Necessidade | Coberta pela app? |
|---|---|
| **A. Fetch** (issue → prompt) | **Não.** A app não lê campos da issue para o workflow. `scripts/jira-fetch` é necessário de qualquer forma. |
| **B. Comentar** com URL do PR | Indireto: o PR aparece no dev panel da issue (se a key estiver no branch/PR). Não posta comentário arbitrário a partir do workflow. |
| **C. Transicionar** "In Review" | Indireto: exigiria mover a transição para uma **Jira Automation rule** disparada por evento de PR. Smart Commits **não** funcionam (committer `claude[bot]` não mapeia para usuário Jira). |

### 10.3 Decisão
- **Manter os scripts REST** (`jira-fetch`, `jira-comment`, `jira-transition`) como fonte da
  verdade: chamadas **síncronas, verificáveis no mesmo run, versionadas e testadas** — o que
  um walking skeleton precisa. Mover B/C para Jira Automation troca código testado por config
  invisível (click-ops) e assíncrona (best-effort), contra a tese do projeto (runbook
  reproduzível).
- **Instalar a app como complemento** (upside grátis): com a issue key no branch/PR (ver
  §4.4), o PR aparece linkado no dev panel da issue com status vivo (aberto/merged/CI). Zero
  código, nenhuma lógica movida para fora do repo.
- Não adicionar Automation rule de transição-por-PR enquanto a transição estiver no código —
  evita transição dupla / fonte da verdade ambígua.

# Jira Coding Agent v3 — ci-fix-agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar dois workflows que fecham o ciclo de CI no PR do `jira-agent`: um notificador (`ci-fix-notifier.yaml`) que avisa em PRs `claude/*` quando o CI falha, e um agente (`ci-fix-agent.yaml`) que, ao receber `/fix`, lê os logs do run que falhou e tenta corrigir o código.

**Architecture:** Dois arquivos YAML novos em `.github/workflows/`, sem código Python. `ci-fix-notifier.yaml` triggera em `workflow_run` (failure do `pull-request`), descobre o PR via `head_sha` e posta convite. `ci-fix-agent.yaml` triggera em `issue_comment`, valida (PR + branch `claude/*` + permissão `write`), parsea `/fix [--max-attempts N]`, conta marcadores `<!-- ci-fix-attempt -->` no PR, ou para com transição Jira ou aciona `claude-code-action`. Loop-guard é o próprio contador; concorrência é tolerada (queue nativa do GitHub).

**Tech Stack:** GitHub Actions YAML, `gh` CLI, `claude-code-action@v1`, scripts bash existentes (`scripts/jira-comment`, `scripts/jira-transition`).

**Spec:** `docs/sdlc/02-design/2026-06-14-ci-fix-agent.md`

---

## File Structure

- Create: `.github/workflows/ci-fix-notifier.yaml`
- Create: `.github/workflows/ci-fix-agent.yaml`
- Modify: `docs/sdlc/CLAUDE.md` (adicionar entradas em 02-design e 03-execution)
- Modify: `HANDOFF.md` (mover do Backlog para In Progress / Next Steps)

Sem testes Python (não há código Python novo). Validação real é manual via PR de teste em branch `claude/*` no GitHub.

---

### Task 1: Criar `ci-fix-notifier.yaml`

**Files:**
- Create: `.github/workflows/ci-fix-notifier.yaml`

- [ ] **Step 1: Escrever o workflow**

```yaml
name: ci-fix-notifier

on:
  workflow_run:
    workflows: ["pull-request"]
    types: [completed]

jobs:
  notify:
    if: >-
      github.event.workflow_run.conclusion == 'failure' &&
      startsWith(github.event.workflow_run.head_branch, 'claude/')
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - name: Find PR and post invite
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          HEAD_SHA: ${{ github.event.workflow_run.head_sha }}
          RUN_URL: ${{ github.event.workflow_run.html_url }}
          REPO: ${{ github.repository }}
        run: |
          pr_number="$(gh pr list \
            --repo "${REPO}" \
            --head "${HEAD_SHA}" \
            --state open \
            --json number \
            --jq '.[0].number // ""')"
          if [[ -z "${pr_number}" ]]; then
            echo "No open PR found for ${HEAD_SHA} — silencing"
            exit 0
          fi
          gh pr comment "${pr_number}" \
            --repo "${REPO}" \
            --body "CI falhou ([ver run](${RUN_URL})). Responda \`/fix\` para tentar corrigir automaticamente."
```

- [ ] **Step 2: Verificar sintaxe**

Run: `python3 -c 'import yaml; yaml.safe_load(open(".github/workflows/ci-fix-notifier.yaml"))'`
Expected: nenhum output (YAML válido).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci-fix-notifier.yaml
git commit -m "feat(ci): add ci-fix-notifier workflow

Triggera em workflow_run (failure do pull-request) e posta
convite /fix no PR correspondente quando a branch é claude/*."
```

---

### Task 2: Criar `ci-fix-agent.yaml` — esqueleto e filtros

**Files:**
- Create: `.github/workflows/ci-fix-agent.yaml`

- [ ] **Step 1: Escrever o workflow com filtros e parsing de `/fix`**

```yaml
name: ci-fix-agent

on:
  issue_comment:
    types: [created]

jobs:
  fix:
    # Filtros mínimos baratos antes do step de validação completa:
    # - é comentário em PR (não em issue)
    # - corpo contém /fix
    # Branch e permissão são checados no primeiro step (precisam de gh api).
    if: >-
      github.event.issue.pull_request != null &&
      contains(github.event.comment.body, '/fix')
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      id-token: write
    steps:
      - name: Validate PR branch and author permission
        id: validate
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.issue.number }}
          COMMENT_AUTHOR: ${{ github.event.comment.user.login }}
        run: |
          branch="$(gh pr view "${PR_NUMBER}" \
            --repo "${REPO}" \
            --json headRefName \
            --jq '.headRefName')"
          if [[ ! "${branch}" =~ ^claude/ ]]; then
            echo "PR branch ${branch} not claude/* — silencing"
            echo "proceed=false" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          permission="$(gh api \
            "repos/${REPO}/collaborators/${COMMENT_AUTHOR}/permission" \
            --jq '.permission')"
          # GitHub returns: admin, write, read, none. Aceitar admin|write.
          if [[ "${permission}" != "admin" && "${permission}" != "write" ]]; then
            echo "Author ${COMMENT_AUTHOR} has permission=${permission} — silencing"
            echo "proceed=false" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          echo "branch=${branch}" >> "$GITHUB_OUTPUT"
          echo "proceed=true" >> "$GITHUB_OUTPUT"

      - name: Parse /fix command
        id: parse
        if: steps.validate.outputs.proceed == 'true'
        env:
          COMMENT_BODY: ${{ github.event.comment.body }}
        run: |
          # Extract --max-attempts N from comment body. Default 3.
          max_attempts=3
          if [[ "${COMMENT_BODY}" =~ --max-attempts[[:space:]]+([0-9]+) ]]; then
            max_attempts="${BASH_REMATCH[1]}"
          fi
          echo "max_attempts=${max_attempts}" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 2: Verificar sintaxe**

Run: `python3 -c 'import yaml; yaml.safe_load(open(".github/workflows/ci-fix-agent.yaml"))'`
Expected: nenhum output (YAML válido).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci-fix-agent.yaml
git commit -m "feat(ci): scaffold ci-fix-agent workflow (filters + /fix parsing)

Triggera em issue_comment. Valida que é PR de branch claude/*,
que o autor do comentário tem permissão write+, e parseia
--max-attempts N (default 3) do corpo do comentário."
```

---

### Task 3: `ci-fix-agent.yaml` — loop-guard via contagem de comentários

**Files:**
- Modify: `.github/workflows/ci-fix-agent.yaml` (acrescentar steps após o `Parse /fix command`)

- [ ] **Step 1: Adicionar step de contagem**

Acrescentar **depois** do step `Parse /fix command`:

```yaml
      - name: Count previous attempts
        id: count
        if: steps.validate.outputs.proceed == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.issue.number }}
        run: |
          # Conta comentários no PR que contêm o marcador.
          # gh pr view retorna comments[*].body — incluir paginação não
          # é necessário para PRs de agente (poucos comentários).
          attempts="$(gh pr view "${PR_NUMBER}" \
            --repo "${REPO}" \
            --json comments \
            --jq '[.comments[] | select(.body | contains("<!-- ci-fix-attempt -->"))] | length')"
          echo "attempts=${attempts}" >> "$GITHUB_OUTPUT"
          echo "Previous attempts: ${attempts}"
```

- [ ] **Step 2: Verificar sintaxe**

Run: `python3 -c 'import yaml; yaml.safe_load(open(".github/workflows/ci-fix-agent.yaml"))'`
Expected: nenhum output.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci-fix-agent.yaml
git commit -m "feat(ci): ci-fix-agent — count previous attempts via comment marker

Conta comentários no PR que contêm <!-- ci-fix-attempt --> via
gh pr view + jq. Resultado vai para steps.count.outputs.attempts."
```

---

### Task 4: `ci-fix-agent.yaml` — branch de esgotamento (max_attempts atingido)

**Files:**
- Modify: `.github/workflows/ci-fix-agent.yaml`

- [ ] **Step 1: Adicionar `Checkout` no topo do job**

O esgotamento usa `scripts/jira-*`, que dependem do repo presente no runner. Adicionar como **primeiro step** do job (antes de `Validate PR branch and author permission`):

```yaml
      - name: Checkout
        uses: actions/checkout@v5
```

- [ ] **Step 2: Adicionar step de esgotamento**

Acrescentar **depois** do step `Count previous attempts`:

```yaml
      - name: Handle exhausted attempts
        id: exhausted
        if: >-
          steps.validate.outputs.proceed == 'true' &&
          steps.count.outputs.attempts >= steps.parse.outputs.max_attempts
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          JIRA_BASE_URL: ${{ secrets.JIRA_BASE_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
          REPO: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.issue.number }}
          BRANCH: ${{ steps.validate.outputs.branch }}
          ATTEMPTS: ${{ steps.count.outputs.attempts }}
          MAX_ATTEMPTS: ${{ steps.parse.outputs.max_attempts }}
        run: |
          # Extract ISSUE_KEY from branch (claude/PLTF-11 → PLTF-11).
          issue_key="${BRANCH#claude/}"
          if [[ ! "${issue_key}" =~ ^[A-Z]+-[0-9]+$ ]]; then
            echo "Branch ${BRANCH} does not encode a valid Jira key — silencing Jira step"
            issue_key=""
          fi

          # Collect run URLs from previous attempt comments for summary.
          run_urls="$(gh pr view "${PR_NUMBER}" \
            --repo "${REPO}" \
            --json comments \
            --jq '[.comments[] | select(.body | contains("<!-- ci-fix-attempt -->")) | .url] | join(", ")')"

          pr_msg="Esgotei ${ATTEMPTS} tentativas (limite: ${MAX_ATTEMPTS}) sem fazer o CI passar. PR permanece aberto para revisão humana. Tentativas: ${run_urls}"
          gh pr comment "${PR_NUMBER}" --repo "${REPO}" --body "${pr_msg}"

          if [[ -n "${issue_key}" ]]; then
            scripts/jira-transition "${issue_key}" "In Progress"
            scripts/jira-comment "${issue_key}" \
              "ci-fix-agent esgotou ${ATTEMPTS} tentativas no PR. Volta para In Progress para revisão humana."
          fi
```

- [ ] **Step 3: Verificar sintaxe**

Run: `python3 -c 'import yaml; yaml.safe_load(open(".github/workflows/ci-fix-agent.yaml"))'`
Expected: nenhum output.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci-fix-agent.yaml
git commit -m "feat(ci): ci-fix-agent — exhaustion branch (comment + Jira transition)

Quando attempts >= max_attempts: posta comentário no PR com
resumo, transiciona issue Jira para In Progress e comenta no Jira.
Checkout adicionado no topo do job para scripts/jira-* funcionarem."
```

---

### Task 5: `ci-fix-agent.yaml` — invocar `claude-code-action` e postar marcador

**Files:**
- Modify: `.github/workflows/ci-fix-agent.yaml`

- [ ] **Step 1: Adicionar step que busca URL do último run que falhou**

Acrescentar **depois** do step `Handle exhausted attempts`:

```yaml
      - name: Find failing run URL
        id: failing
        if: >-
          steps.validate.outputs.proceed == 'true' &&
          steps.count.outputs.attempts < steps.parse.outputs.max_attempts
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.issue.number }}
        run: |
          # Head SHA do PR.
          head_sha="$(gh pr view "${PR_NUMBER}" \
            --repo "${REPO}" \
            --json headRefOid \
            --jq '.headRefOid')"
          # Último run do pull-request workflow nesse SHA com conclusão failure.
          run_url="$(gh run list \
            --repo "${REPO}" \
            --workflow=pull-request.yaml \
            --commit "${head_sha}" \
            --status failure \
            --json url \
            --jq '.[0].url // ""')"
          if [[ -z "${run_url}" ]]; then
            echo "No failing pull-request run for ${head_sha}"
            echo "url=" >> "$GITHUB_OUTPUT"
          else
            echo "url=${run_url}" >> "$GITHUB_OUTPUT"
          fi
```

- [ ] **Step 2: Adicionar step de montagem do prompt**

Acrescentar **depois** do `Find failing run URL`:

```yaml
      - name: Build prompt
        id: prompt
        if: >-
          steps.validate.outputs.proceed == 'true' &&
          steps.count.outputs.attempts < steps.parse.outputs.max_attempts
        env:
          BRANCH: ${{ steps.validate.outputs.branch }}
          RUN_URL: ${{ steps.failing.outputs.url }}
          ATTEMPTS: ${{ steps.count.outputs.attempts }}
          MAX_ATTEMPTS: ${{ steps.parse.outputs.max_attempts }}
        run: |
          # attempts é a contagem antes desta tentativa; a tentativa atual
          # é attempts+1.
          current_attempt=$((ATTEMPTS + 1))
          delimiter="EOF_$(openssl rand -hex 16)"
          {
            echo "AGENT_PROMPT<<${delimiter}"
            cat <<PROMPT
CI falhou no PR ${BRANCH} (tentativa ${current_attempt} de ${MAX_ATTEMPTS}).
Logs de falha: ${RUN_URL}

Leia os logs, identifique a causa, corrija o código.
Faça commit e push na branch existente — não crie branch nova.
Não altere código não relacionado à falha.
PROMPT
            echo "${delimiter}"
          } >> "$GITHUB_ENV"
          echo "current_attempt=${current_attempt}" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 3: Adicionar step que troca o checkout para a branch do PR**

O `Checkout` inicial (Task 4 Step 1) pegou o default branch para que os scripts `scripts/jira-*` estivessem disponíveis. Agora precisamos da branch `claude/*` para o agente trabalhar. Um segundo `actions/checkout@v5` substitui o conteúdo do `GITHUB_WORKSPACE`:

```yaml
      - name: Checkout PR branch
        if: >-
          steps.validate.outputs.proceed == 'true' &&
          steps.count.outputs.attempts < steps.parse.outputs.max_attempts
        uses: actions/checkout@v5
        with:
          ref: ${{ steps.validate.outputs.branch }}
          fetch-depth: 0
```

Acrescentar **depois** do `Build prompt`.

- [ ] **Step 4: Adicionar step que aciona `claude-code-action`**

Acrescentar **depois** do `Checkout PR branch`:

```yaml
      - name: Implement fix with Claude
        id: claude
        if: >-
          steps.validate.outputs.proceed == 'true' &&
          steps.count.outputs.attempts < steps.parse.outputs.max_attempts
        uses: anthropics/claude-code-action@v1
        with:
          prompt: ${{ env.AGENT_PROMPT }}
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          claude_args: >-
            --model claude-opus-4-8
            --dangerously-skip-permissions
          show_full_output: true
```

- [ ] **Step 5: Adicionar step que posta marcador de tentativa**

Acrescentar **depois** do `Implement fix with Claude`:

```yaml
      - name: Post attempt marker
        if: >-
          always() &&
          steps.validate.outputs.proceed == 'true' &&
          steps.count.outputs.attempts < steps.parse.outputs.max_attempts
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.issue.number }}
          CURRENT_ATTEMPT: ${{ steps.prompt.outputs.current_attempt }}
          MAX_ATTEMPTS: ${{ steps.parse.outputs.max_attempts }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
          CLAUDE_OUTCOME: ${{ steps.claude.outcome }}
        run: |
          gh pr comment "${PR_NUMBER}" \
            --repo "${REPO}" \
            --body "<!-- ci-fix-attempt -->
Tentativa ${CURRENT_ATTEMPT} de ${MAX_ATTEMPTS} (claude-code-action: ${CLAUDE_OUTCOME}). [Ver run](${RUN_URL})."
```

Notas sobre o marcador:
- `if: always()` garante o comentário mesmo se `claude-code-action` falhar.
- O comentário inteiro contém `<!-- ci-fix-attempt -->`, então o próximo run conta corretamente independente de sucesso/falha do agente.
- `steps.claude.outcome` retorna `success`, `failure`, ou `cancelled` — informativo no comentário, não usado em lógica.

- [ ] **Step 6: Verificar sintaxe**

Run: `python3 -c 'import yaml; yaml.safe_load(open(".github/workflows/ci-fix-agent.yaml"))'`
Expected: nenhum output.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/ci-fix-agent.yaml
git commit -m "feat(ci): ci-fix-agent — invoke claude-code-action and post marker

Busca URL do último run de pull-request com failure no head SHA do PR,
monta prompt com tentativa N/MAX, faz checkout da branch claude/*,
aciona claude-code-action e posta comentário com marcador
<!-- ci-fix-attempt --> + outcome + link do run."
```

---

### Task 6: Atualizar `docs/sdlc/CLAUDE.md`

**Files:**
- Modify: `docs/sdlc/CLAUDE.md`

- [ ] **Step 1: Adicionar entrada em 02-design**

Acrescentar uma linha na tabela de 02-design, **depois** da linha `2026-06-13-jira-coding-agent-v3-sec-008.md`:

```markdown
| [2026-06-14-ci-fix-agent.md](02-design/2026-06-14-ci-fix-agent.md) | Jira Coding Agent v3 — ci-fix-agent (auto-fix de CI) |
```

- [ ] **Step 2: Adicionar entrada em 03-execution**

Acrescentar uma linha na tabela de 03-execution, **depois** da linha `2026-06-13-jira-coding-agent-v3-sec-008.md`:

```markdown
| [2026-06-14-ci-fix-agent.md](03-execution/2026-06-14-ci-fix-agent.md) | Jira Coding Agent v3 — ci-fix-agent — Implementation Plan |
```

- [ ] **Step 3: Verificar diff**

Run: `git diff docs/sdlc/CLAUDE.md`
Expected: duas linhas adicionadas, uma em cada tabela.

- [ ] **Step 4: Commit**

```bash
git add docs/sdlc/CLAUDE.md
git commit -m "docs(sdlc): registrar specs do ci-fix-agent em 02-design e 03-execution"
```

---

### Task 7: Atualizar `HANDOFF.md`

**Files:**
- Modify: `HANDOFF.md`

- [ ] **Step 1: Substituir o bloco `In Progress`**

Trocar:

```markdown
## In Progress

Nada em andamento. v3/SEC-008 mergeado.

Próximo: segundo spec da v3 (ver Backlog).
```

Por:

```markdown
## In Progress

**Jira Coding Agent v3 — ci-fix-agent** (segundo spec da v3). Spec: `docs/sdlc/02-design/2026-06-14-ci-fix-agent.md`. Plano: `docs/sdlc/03-execution/2026-06-14-ci-fix-agent.md`.
```

- [ ] **Step 2: Atualizar bullet do v3 no Backlog**

Trocar:

```markdown
- **Jira Coding Agent v3** (3 specs restantes) — fatiamento decidido: um spec por item. Itens: `pr-agent.yaml` (auto-fix de CI no PR do agente via action oficial em `workflow_run`/`issue_comment`, com loop-guard), dry-run via `workflow_dispatch`, extração da lógica para CLI Python testado. Gate de ambiguidade dropado: a premissa é que só issues refinadas (negócio + técnico) são delegadas ao agente, então o risco de ambiguidade chegar é absorvido pelo processo upstream.
```

Por:

```markdown
- **Jira Coding Agent v3** (2 specs restantes) — `ci-fix-agent` em andamento (ver In Progress). Itens pendentes: dry-run via `workflow_dispatch`, extração da lógica para CLI Python testado. Gate de ambiguidade dropado: a premissa é que só issues refinadas (negócio + técnico) são delegadas ao agente, então o risco de ambiguidade chegar é absorvido pelo processo upstream.
```

- [ ] **Step 3: Atualizar `Next Steps`**

Trocar:

```markdown
## Next Steps

- **Validação manual v3/SEC-008** (Task 5): disparar `gh workflow run jira-agent.yaml -f jira_issue=PLTF-11`; run verde → sem artefato. Forçar falha → artefato com 7d.
- **Próximo spec da v3**: escolher entre `pr-agent.yaml` (auto-fix CI), dry-run, ou CLI Python.
```

Por:

```markdown
## Next Steps

- Executar o plano `docs/sdlc/03-execution/2026-06-14-ci-fix-agent.md` (ci-fix-agent + ci-fix-notifier).
- Após merge: validação manual disparando uma falha intencional de CI em um PR `claude/*` e respondendo `/fix`.
```

- [ ] **Step 4: Verificar diff**

Run: `git diff HANDOFF.md`
Expected: bloco `In Progress` atualizado, bullet do v3 no Backlog atualizado, `Next Steps` atualizado. Nada mais.

- [ ] **Step 5: Commit**

```bash
git add HANDOFF.md
git commit -m "docs(handoff): ci-fix-agent in progress, v3 backlog atualizado"
```

---

### Task 8: Abrir PR

**Files:**
- (n/a — operação git/gh)

- [ ] **Step 1: Push branch**

```bash
git push --set-upstream origin dev
```

(Se `dev` já estiver sincronizada com `origin/dev`, basta `git push origin dev`.)

- [ ] **Step 2: Gerar descrição do PR**

Salvar em `/tmp/ci-fix-agent-pr.txt`:

```markdown
## Summary

Adiciona dois workflows que fecham o ciclo de CI no PR do `jira-agent`:

- `ci-fix-notifier.yaml` — detecta falha de CI em branch `claude/*` e posta convite `/fix` no PR.
- `ci-fix-agent.yaml` — recebe `/fix [--max-attempts N]` (default 3), conta tentativas via marcador `<!-- ci-fix-attempt -->`, aciona `claude-code-action`, ou esgota e transiciona Jira para "In Progress".

Sem código Python novo. Sem secrets novos.

Spec: `docs/sdlc/02-design/2026-06-14-ci-fix-agent.md`
Plano: `docs/sdlc/03-execution/2026-06-14-ci-fix-agent.md`

## Test plan

- [ ] CI verde do próprio PR (lint/format/tests inalterados — apenas YAML novo).
- [ ] Pós-merge: forçar falha intencional em um PR de teste em branch `claude/*`. Confirmar:
  - `ci-fix-notifier` posta convite automaticamente.
  - `/fix` aciona o agente e posta marcador `<!-- ci-fix-attempt -->`.
  - `/fix --max-attempts 1` esgota imediatamente após primeira tentativa.
  - Esgotamento posta comentário + transiciona Jira para In Progress.
  - Usuário sem `write` postando `/fix` é silenciosamente ignorado.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 3: Abrir PR contra `main`**

```bash
gh pr create \
  --base main \
  --head dev \
  --title "feat(ci): ci-fix-agent (auto-fix de CI no PR do jira-agent)" \
  --body-file /tmp/ci-fix-agent-pr.txt
```

- [ ] **Step 4: Aguardar CI**

Run: `gh pr checks --watch`
Expected: ci verde. (O `ci-fix-notifier`/`ci-fix-agent` **não** rodam neste PR — eles só disparam em `workflow_run`/`issue_comment`. O `pull-request.yaml` roda normalmente.)

---

### Task 9: Validação manual pós-merge

> Esta task **não tem commits**. É a validação real do feature, executada depois do merge em `main`.

- [ ] **Step 1: Sincronizar `dev` com `main`**

```bash
git checkout main && git pull --ff-only
git checkout dev && git reset --hard origin/main && git push --force-with-lease origin dev
```

- [ ] **Step 2: Setup — criar PR de teste com falha de CI**

Disparar `jira-agent` para uma issue Jira que produza código com testes quebrados. Alternativa: criar manualmente um PR de teste com branch `claude/PLTF-test-cifix` contendo um teste que falha (ex: `assert 1 == 2`).

```bash
gh workflow run jira-agent.yaml -f jira_issue=PLTF-XX  # ou criar PR manual
```

Esperar até que o PR esteja aberto e o `pull-request.yaml` tenha rodado e falhado.

- [ ] **Step 3: Verificar — `ci-fix-notifier` posta convite**

Olhar a aba de comentários do PR. Esperado: comentário automático começando com "CI falhou ([ver run](...))" e mencionando `/fix`.

```bash
gh pr view <PR_NUMBER> --json comments --jq '.comments[] | .body' | grep -i "/fix"
```

Expected: pelo menos uma linha contendo `/fix`.

- [ ] **Step 4: Verificar — `/fix` aciona o agente**

Postar comentário no PR com texto `/fix`. Acompanhar:

```bash
gh run watch <RUN_ID_DO_CI_FIX_AGENT>
```

Expected: run conclui. Comentário com marcador `<!-- ci-fix-attempt -->` aparece no PR. `pull-request.yaml` re-dispara no novo commit (se Claude fez push).

- [ ] **Step 5: Verificar — `--max-attempts 1` esgota imediatamente após primeira tentativa**

Depois do Step 4 (já há 1 tentativa registrada), postar `/fix --max-attempts 1` no PR.

Expected: o workflow encontra `attempts=1` (já há um marcador), entra no branch de esgotamento, posta comentário "Esgotei 1 tentativas (limite: 1)" e transiciona a issue Jira para "In Progress".

- [ ] **Step 6: Verificar — usuário sem permissão é silenciado**

Se houver outra conta com permissão `read` no repo (ou se o repo for tornado público temporariamente), postar `/fix` desse usuário. Caso o setup atual não permita o teste, marcar como N/A com nota no HANDOFF.

Expected: nenhum comentário novo, nenhum run de agente (apenas o run inicial do `ci-fix-agent` que sai com `proceed=false`).

- [ ] **Step 7: Atualizar HANDOFF**

Se a validação revelou problemas, abrir issue ou seguir spec adicional. Caso contrário, atualizar `HANDOFF.md`:

- Mover `ci-fix-agent` de `In Progress` para histórico (`Why` ou similar).
- Próximo: terceiro spec da v3 (dry-run ou CLI Python).

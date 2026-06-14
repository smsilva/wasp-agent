# Jira Coding Agent v3 — SEC-008 fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restringir o artefato `claude-execution-log-<ISSUE_KEY>.tar.gz` a runs com falha e baixar retenção de 30 para 7 dias, fechando SEC-008.

**Architecture:** Edit cirúrgico em `.github/workflows/jira-agent.yaml` (dois `if: always()` → `if: failure()`; `retention-days: 30` → `7`). Sem código Python novo. SEC-008 arquivado e HANDOFF limpo.

**Tech Stack:** GitHub Actions YAML, markdown.

**Spec:** `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v3-sec-008.md`

---

## File Structure

- Modify: `.github/workflows/jira-agent.yaml:94-118` (2 steps; 3 valores)
- Modify: `docs/security/issues/SEC-008-jira-agent-execution-log-artifact.md` (frontmatter `status: open` → `resolved`)
- Move: `docs/security/issues/SEC-008-jira-agent-execution-log-artifact.md` → `docs/security/issues/archived/`
- Modify: `HANDOFF.md` (remove bullet SEC-008 de Known Broken; remove "Resolver SEC-008" do bullet v3 em Backlog)

Sem testes Python (não há código novo). Validação real é manual em GitHub Actions (spec §4).

---

### Task 1: Apply workflow change

**Files:**
- Modify: `.github/workflows/jira-agent.yaml:94-118`

- [ ] **Step 1: Edit `Collect Claude execution log` step**

Localizar o bloco (linha 94 hoje) e trocar `if: always()` por `if: failure()`:

```yaml
      - name: Collect Claude execution log
        if: failure()
        env:
          ISSUE_KEY: ${{ env.ISSUE_KEY }}
        run: |
          log_dir="$(mktemp --directory)"
          src="/home/runner/work/_temp/claude-execution-output.json"
          if [[ -f "${src}" ]]; then
            cp "${src}" "${log_dir}/claude-execution-output.json"
          else
            echo "claude-execution-output.json not produced" \
              > "${log_dir}/MISSING.txt"
          fi
          tar --create --gzip \
            --file "claude-execution-log-${ISSUE_KEY}.tar.gz" \
            --directory "${log_dir}" \
            .
```

- [ ] **Step 2: Edit `Upload Claude execution log` step**

Localizar o bloco (linha 112 hoje) e trocar `if: always()` por `if: failure()` e `retention-days: 30` por `7`:

```yaml
      - name: Upload Claude execution log
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: claude-execution-log-${{ env.ISSUE_KEY }}
          path: claude-execution-log-${{ env.ISSUE_KEY }}.tar.gz
          retention-days: 7
```

- [ ] **Step 3: Verificar diff**

Run: `git diff .github/workflows/jira-agent.yaml`
Expected: exatamente 3 linhas alteradas — dois `if:` e um `retention-days:`. Nada mais.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/jira-agent.yaml
git commit -m "fix(jira-agent): SEC-008 — gate execution log artifact on failure

Aplicar mitigações (1) + (4) do SEC-008.md:
- if: always() → if: failure() em Collect/Upload do artefato
- retention-days: 30 → 7

Runs verdes deixam de produzir log post-mortem; runs vermelhos
mantêm 7 dias de retenção pra debug."
```

---

### Task 2: Arquivar SEC-008

**Files:**
- Modify: `docs/security/issues/SEC-008-jira-agent-execution-log-artifact.md`
- Move: `docs/security/issues/SEC-008-jira-agent-execution-log-artifact.md` → `docs/security/issues/archived/SEC-008-jira-agent-execution-log-artifact.md`

- [ ] **Step 1: Atualizar frontmatter**

Trocar no topo do arquivo:

```diff
 ---
 id: SEC-008
 severity: Low
-status: open
+status: resolved
 opened: 2026-06-13
+resolved: 2026-06-13
 ---
```

- [ ] **Step 2: Mover para `archived/`**

```bash
git mv docs/security/issues/SEC-008-jira-agent-execution-log-artifact.md \
       docs/security/issues/archived/SEC-008-jira-agent-execution-log-artifact.md
```

- [ ] **Step 3: Verificar**

Run: `ls docs/security/issues/ docs/security/issues/archived/ | grep SEC-008`
Expected: arquivo aparece **só** em `archived/`.

- [ ] **Step 4: Commit**

```bash
git add docs/security/issues/
git commit -m "docs(security): SEC-008 resolved, archive"
```

---

### Task 3: Atualizar HANDOFF.md

**Files:**
- Modify: `HANDOFF.md:29-32` (Known Broken — remover bullet SEC-008)
- Modify: `HANDOFF.md:58` (Backlog v3 — remover "Resolver SEC-008")

- [ ] **Step 1: Remover bullet de Known Broken**

Trocar o bloco atual:

```markdown
## Known Broken

- **SEC-008** (Low, *unexpected*): artefato `claude-execution-log-<ISSUE_KEY>.tar.gz` é uploaded em `if: always()` com `retention-days: 30`, expondo body da issue + tool outputs + env vars do agente. Plano: apertar para `if: failure()` + `retention-days: 7` na v3. Spec: `docs/security/issues/SEC-008-jira-agent-execution-log-artifact.md`.
```

Por:

```markdown
## Known Broken

Nada.
```

- [ ] **Step 2: Limpar referência no Backlog**

Trocar:

```markdown
- **Jira Coding Agent v3** — `pr-agent.yaml` (auto-fix de CI no PR do agente via action oficial em `workflow_run`/`issue_comment`, com loop-guard), dry-run via `workflow_dispatch`, extração da lógica para CLI Python testado. Resolver SEC-008. Gate de ambiguidade dropado: a premissa é que só issues refinadas (negócio + técnico) são delegadas ao agente, então o risco de ambiguidade chegar é absorvido pelo processo upstream.
```

Por:

```markdown
- **Jira Coding Agent v3** — `pr-agent.yaml` (auto-fix de CI no PR do agente via action oficial em `workflow_run`/`issue_comment`, com loop-guard), dry-run via `workflow_dispatch`, extração da lógica para CLI Python testado. Gate de ambiguidade dropado: a premissa é que só issues refinadas (negócio + técnico) são delegadas ao agente, então o risco de ambiguidade chegar é absorvido pelo processo upstream.
```

- [ ] **Step 3: Verificar diff**

Run: `git diff HANDOFF.md`
Expected: bullet SEC-008 removido de Known Broken (substituído por "Nada."), `Resolver SEC-008.` removido do bullet do v3 no Backlog. Nada mais.

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md
git commit -m "docs(handoff): SEC-008 resolved, drop from known broken + v3 scope"
```

---

### Task 4: Abrir PR

**Files:**
- (n/a — operação git/gh)

- [ ] **Step 1: Push branch**

```bash
git push --set-upstream origin docs/jira-agent-v3-sec-008-spec
```

(Branch atual já contém o commit do spec da v3; os três commits desta task vão por cima.)

- [ ] **Step 2: Abrir PR contra `main`**

```bash
gh pr create --base main --head docs/jira-agent-v3-sec-008-spec \
  --title "fix(jira-agent): SEC-008 — gate execution log artifact on failure" \
  --body-file /tmp/jira-agent-v3-sec-008-pr.txt
```

Gerar `/tmp/jira-agent-v3-sec-008-pr.txt` antes com o resumo do spec + checklist de validação manual.

- [ ] **Step 3: Aguardar CI**

Run: `gh pr checks --watch`
Expected: ci.yaml verde. (O jira-agent.yaml **não** roda neste PR — ele só dispara em `repository_dispatch`/`workflow_dispatch`.)

---

### Task 5: Validação manual pós-merge (spec §4)

> Esta task **não tem commits**. É a validação real do fix, executada depois do merge em `main`.

- [ ] **Step 1: Sincronizar `dev` com `main`**

```bash
git checkout main && git pull --ff-only
git checkout dev && git reset --hard origin/main && git push --force-with-lease origin dev
```

- [ ] **Step 2: Run verde — disparar PLTF-11 e conferir ausência de artefato**

Disparar via Jira (issue → menu `• • •` → Automation → "Jira Coding Agent — manual trigger"). Ou via:

```bash
gh workflow run jira-agent.yaml -f jira_issue=PLTF-11
```

Esperar o run terminar verde. Conferir:

```bash
gh run list --workflow=jira-agent.yaml --limit 1
gh run view <RUN_ID> --log | grep -i artifact || echo "no artifact step — expected"
```

Expected: **nenhum** artefato `claude-execution-log-*` listado em `gh run view <RUN_ID>` (aba Artifacts vazia).

- [ ] **Step 3: Run vermelho — forçar falha e conferir presença de artefato com 7d**

Disparar com issue inexistente (validação de regex passa, mas `scripts/jira-fetch` vai falhar com 404):

```bash
gh workflow run jira-agent.yaml -f jira_issue=PLTF-99999
```

Esperar o run terminar vermelho. Conferir na UI Actions → Artifacts:

Expected: artefato `claude-execution-log-PLTF-99999` presente, badge mostrando "Expires in 7 days".

- [ ] **Step 4: Confirmar fechamento**

Atualizar HANDOFF se algo da validação revelar surpresa. Caso contrário, SEC-008 segue resolvido.

# CI Pull-Request Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir `.github/workflows/e2e.yaml` por `pull-request.yaml` com dois jobs — `checks` (lint, format, lock, unit tests, path detection) e `e2e` (condicional por paths, verbose, upload de log).

**Architecture:** Job `checks` roda sempre e expõe `run_e2e` como output. Job `e2e` depende de `checks` e só executa quando `run_e2e == 'true'`. O script `ci-check-e2e-paths` usa `git diff` para determinar o output. O script `e2e-with-debug` recebe fix de `set -o pipefail` para propagar exit code do pytest através do `tee`.

**Tech Stack:** GitHub Actions, bash, uv, ruff, pytest, k3d.

---

## File Map

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `scripts/e2e-with-debug` | modificar | fix pipefail |
| `scripts/ci-check-e2e-paths` | criar | detectar paths relevantes via git diff |
| `.github/workflows/pull-request.yaml` | criar | workflow completo (checks + e2e) |
| `.github/workflows/e2e.yaml` | deletar | substituído por pull-request.yaml |

---

### Task 1: Fix `scripts/e2e-with-debug` — propagar exit code do pytest

**Files:**
- Modify: `scripts/e2e-with-debug`

- [ ] **Step 1: Verificar o bug atual**

```bash
bash -c 'false | tee /dev/null'; echo "exit: $?"
```

Expected: `exit: 0` — confirma que sem pipefail o exit code é do `tee`, não do comando que falhou.

- [ ] **Step 2: Adicionar `set -o pipefail` no script**

Conteúdo final de `scripts/e2e-with-debug`:

```bash
#!/bin/bash
set -o pipefail

log_file="$(pwd)/logs/e2e-$(date +%Y%m%dT%H%M%S).log"
mkdir --parents "$(dirname "${log_file}")"

uv run pytest tests/e2e/ -m e2e --no-cov -v -s --log-cli-level=DEBUG -x 2>&1 | tee "${log_file}"

echo ""
echo "Log: ${log_file}"
```

- [ ] **Step 3: Verificar que pipefail agora propaga o exit code**

```bash
bash -c 'set -o pipefail; false | tee /dev/null'; echo "exit: $?"
```

Expected: `exit: 1`

- [ ] **Step 4: Verificar sintaxe do script**

```bash
bash -n scripts/e2e-with-debug
```

Expected: nenhuma saída (sem erros de sintaxe).

- [ ] **Step 5: Commit**

```bash
git add scripts/e2e-with-debug
git commit -m "fix(scripts): propagate pytest exit code through tee with pipefail"
```

---

### Task 2: Criar `scripts/ci-check-e2e-paths`

**Files:**
- Create: `scripts/ci-check-e2e-paths`

O script lê a variável de ambiente `BASE_REF` (passada pelo workflow) e `GITHUB_OUTPUT` (fornecida pelo runner do GitHub Actions). Localmente, quando `GITHUB_OUTPUT` não existe, faz print para debug.

- [ ] **Step 1: Criar o script**

```bash
#!/bin/bash

changed=$(git diff --name-only "origin/${BASE_REF}...HEAD")

if echo "${changed}" | grep -qE '^(wasp/|tests/e2e/|pyproject\.toml|uv\.lock)'; then
  echo "run_e2e=true" >> "${GITHUB_OUTPUT}"
else
  echo "run_e2e=false" >> "${GITHUB_OUTPUT}"
fi
```

- [ ] **Step 2: Tornar executável**

```bash
chmod +x scripts/ci-check-e2e-paths
```

- [ ] **Step 3: Verificar sintaxe**

```bash
bash -n scripts/ci-check-e2e-paths
```

Expected: nenhuma saída.

- [ ] **Step 4: Testar localmente — caso e2e deve rodar**

Simula mudança em `wasp/`:

```bash
GITHUB_OUTPUT=/tmp/gh-output BASE_REF=main \
  bash -c '
    git diff --name-only origin/main...HEAD | grep -q . || echo "wasp/notifier.py" > /tmp/mock-diff
    changed=$(echo "wasp/notifier.py")
    if echo "${changed}" | grep -qE "^(wasp/|tests/e2e/|pyproject\.toml|uv\.lock)"; then
      echo "run_e2e=true" >> /tmp/gh-output
    else
      echo "run_e2e=false" >> /tmp/gh-output
    fi
  '
cat /tmp/gh-output
```

Expected: `run_e2e=true`

- [ ] **Step 5: Testar localmente — caso e2e não deve rodar**

```bash
rm -f /tmp/gh-output
changed="docs/HANDOFF.md"
GITHUB_OUTPUT=/tmp/gh-output bash -c '
  changed="docs/HANDOFF.md"
  if echo "${changed}" | grep -qE "^(wasp/|tests/e2e/|pyproject\.toml|uv\.lock)"; then
    echo "run_e2e=true" >> "${GITHUB_OUTPUT}"
  else
    echo "run_e2e=false" >> "${GITHUB_OUTPUT}"
  fi
'
cat /tmp/gh-output
```

Expected: `run_e2e=false`

- [ ] **Step 6: Commit**

```bash
git add scripts/ci-check-e2e-paths
git commit -m "feat(scripts): detect e2e-relevant path changes via git diff"
```

---

### Task 3: Criar `.github/workflows/pull-request.yaml`

**Files:**
- Create: `.github/workflows/pull-request.yaml`

- [ ] **Step 1: Criar o arquivo**

```yaml
name: pull-request

on:
  pull_request:
    branches:
      - main
    paths:
      - 'main.py'
      - 'wasp/**'
      - 'tests/**'
      - 'pyproject.toml'
      - 'uv.lock'

jobs:
  checks:
    runs-on: ubuntu-latest
    outputs:
      run_e2e: ${{ steps.check-paths.outputs.run_e2e }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync --group dev

      - name: Lint
        run: uv run ruff check .

      - name: Format check
        run: uv run ruff format --check .

      - name: Lock check
        run: uv lock --check

      - name: Unit tests
        run: make test

      - name: Check e2e paths
        id: check-paths
        env:
          BASE_REF: ${{ github.base_ref }}
        run: scripts/ci-check-e2e-paths

  e2e:
    needs: [checks]
    if: needs.checks.outputs.run_e2e == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync --group dev

      - name: Install k3d
        run: curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash

      - name: Run E2E tests
        env:
          ANTHROPIC_BASE_URL: ${{ secrets.ANTHROPIC_BASE_URL }}
          ANTHROPIC_AUTH_TOKEN: ${{ secrets.ANTHROPIC_AUTH_TOKEN }}
        run: make e2e-with-debug
        timeout-minutes: 10

      - name: Upload E2E logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-logs
          path: logs/e2e-*.log
          retention-days: 7
```

- [ ] **Step 2: Verificar YAML válido**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/pull-request.yaml'))" && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/pull-request.yaml
git commit -m "feat(ci): add pull-request workflow with checks and conditional e2e job"
```

---

### Task 4: Deletar `.github/workflows/e2e.yaml`

**Files:**
- Delete: `.github/workflows/e2e.yaml`

- [ ] **Step 1: Remover o arquivo**

```bash
git rm .github/workflows/e2e.yaml
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore(ci): remove e2e.yaml replaced by pull-request.yaml"
```

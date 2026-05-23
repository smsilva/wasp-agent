**Date:** 2026-05-21  
**Status:** Approved  
**Scope:** `.github/workflows/`, `scripts/`

# CI — Pull Request Workflow

## Problem

O workflow `e2e.yaml` atual tem três problemas:

1. Não roda `make test` (unit tests + coverage) — só e2e.
2. Roda e2e incondicionalmente em todo PR, mesmo quando apenas docs ou config não-relacionada mudam.
3. O script `scripts/e2e-with-debug` não propaga o exit code do pytest através do `tee` (bug de pipefail).

## Solução

Substituir `e2e.yaml` por `pull-request.yaml` com dois jobs:

- `checks`: lint, format, lock, unit tests — sempre.
- `e2e`: e2e verboso + upload de log — só quando paths relevantes mudaram.

## Arquivos alterados

| Arquivo | Ação |
|---|---|
| `.github/workflows/e2e.yaml` | deletar |
| `.github/workflows/pull-request.yaml` | criar |
| `scripts/ci-check-e2e-paths` | criar |
| `scripts/e2e-with-debug` | fix `set -o pipefail` |

## Workflow `pull-request.yaml`

**Trigger:** `pull_request` → branch `main`

**Paths:** `main.py`, `wasp/**`, `tests/**`, `pyproject.toml`, `uv.lock`

### Job `checks`

Steps em ordem:

1. `actions/checkout@v4`
2. `astral-sh/setup-uv@v4`
3. `uv sync --group dev`
4. `uv run ruff check .`
5. `uv run ruff format --check .`
6. `uv lock --check`
7. `make test`
8. `scripts/ci-check-e2e-paths` — step output `run_e2e=true/false`

O step 8 expõe o output no nível do job via `outputs`:

```yaml
outputs:
  run_e2e: ${{ steps.check-paths.outputs.run_e2e }}
```

### Job `e2e`

Condição: `needs: [checks]`, `if: needs.checks.outputs.run_e2e == 'true'`

Steps:

1. `actions/checkout@v4`
2. `astral-sh/setup-uv@v4`
3. `uv sync --group dev`
4. Install k3d (curl install script)
5. `make e2e-with-debug` — env: `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`
6. `actions/upload-artifact@v4` — `if: always()`, path `logs/e2e-*.log`, retention 7 dias

## Script `scripts/ci-check-e2e-paths`

```bash
#!/bin/bash
changed=$(git diff --name-only "origin/${BASE_REF}...HEAD")
if echo "${changed}" | grep -qE '^(wasp/|tests/e2e/|pyproject\.toml|uv\.lock)'; then
  echo "run_e2e=true" >> "${GITHUB_OUTPUT}"
else
  echo "run_e2e=false" >> "${GITHUB_OUTPUT}"
fi
```

`BASE_REF` é passado via env no step do workflow: `BASE_REF: ${{ github.base_ref }}`.

## Fix `scripts/e2e-with-debug`

Adicionar `set -o pipefail` logo após o shebang para que o exit code do pytest
atravesse o `tee` corretamente. Sem isso, o CI passa mesmo quando o pytest falha.
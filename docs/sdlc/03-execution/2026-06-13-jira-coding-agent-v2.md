# Jira Coding Agent v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir os stubs do `jira-agent.yaml` por implementação real: ao disparar uma issue, o agente lê a issue, implementa via `claude-code-action`, abre um PR e devolve a URL ao Jira transicionando a issue para "In Review".

**Architecture:** O workflow `jira-agent.yaml` monta um prompt a partir da issue (`scripts/jira-fetch`, REST + `renderedFields`), roda `anthropics/claude-code-action@v1` (App oficial "Claude" cunha o token de git internamente a partir do `CLAUDE_CODE_OAUTH_TOKEN`), garante o PR (`scripts/ensure-pr`, find-or-create via `gh`) e devolve ao Jira (`scripts/jira-comment` + `scripts/jira-transition`). O lado Jira fica em bash testado por pytest; o lado GitHub (action + `ensure-pr`) é validado por e2e manual.

**Tech Stack:** GitHub Actions, `anthropics/claude-code-action@v1`, bash, curl, jq, `gh` CLI, Jira Cloud REST API v3, pytest (mock HTTP server).

**Spec:** `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md`

---

## File Structure

- **Create** `scripts/jira-fetch` — bash: `GET issue?expand=renderedFields&fields=summary`, emite um prompt markdown (instrução + summary + description HTML) em stdout.
- **Create** `tests/test_jira_fetch.py` — roda o script contra um mock HTTP server; valida método/endpoint/query/auth e o conteúdo do prompt.
- **Create** `scripts/jira-transition` — bash: resolve o id da transição por nome (case-insensitive) via `GET .../transitions` e faz `POST .../transitions`.
- **Create** `tests/test_jira_transition.py` — mock server com GET (lista de transições) + POST (captura); valida o match por nome e o id no body.
- **Create** `scripts/ensure-pr` — bash + `gh`: dado o branch e a issue key, encontra o PR existente ou cria um (título com a key); imprime a URL. Sem unit test (glue de GitHub; validado por e2e).
- **Modify** `.github/workflows/jira-agent.yaml` — substitui os 5 stubs por: build prompt → `claude-code-action` → `ensure-pr` → comment + transition; adiciona bloco `permissions:`.
- **Rewrite** `docs/runbooks/jira-coding-agent-setup.md` — setup v2 como caminho corrente.
- **Modify** `HANDOFF.md`, `docs/sdlc/CLAUDE.md`, `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md` — registrar v2 implementada.

Convenção de bash do projeto (regras globais): sem extensão no executável, long-form CLI options, 2-space indent, locais minúsculos, sempre aspas em `"${var}"`, args obrigatórios via `${var?}`, `set -e` para sequência.

---

## Task 1: `scripts/jira-fetch`

**Files:**
- Create: `scripts/jira-fetch`
- Test: `tests/test_jira_fetch.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_jira_fetch.py`:

```python
import base64
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "jira-fetch"

captured: dict = {}

ISSUE_JSON = {
    "fields": {"summary": "Extract parse_session_id helper"},
    "renderedFields": {"description": "<p>Refactor the duplicated parser.</p>"},
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        captured["path"] = self.path
        captured["auth"] = self.headers["Authorization"]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(ISSUE_JSON).encode())

    def log_message(self, *args):  # silence server logging
        pass


def test_jira_fetch_emits_prompt():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    result = subprocess.run(
        [str(SCRIPT), "PROJ-1"],
        env={
            **os.environ,
            "JIRA_BASE_URL": f"http://127.0.0.1:{port}",
            "JIRA_EMAIL": "bot@example.com",
            "JIRA_API_TOKEN": "secret-token",
        },
        capture_output=True,
        text=True,
    )
    server.shutdown()

    assert result.returncode == 0, result.stderr
    assert captured["path"].startswith("/rest/api/3/issue/PROJ-1")
    assert "expand=renderedFields" in captured["path"]
    expected_auth = base64.b64encode(b"bot@example.com:secret-token").decode()
    assert captured["auth"] == f"Basic {expected_auth}"
    assert "PROJ-1" in result.stdout
    assert "Extract parse_session_id helper" in result.stdout
    assert "Refactor the duplicated parser." in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_jira_fetch.py -v`
Expected: FAIL — script não existe (returncode != 0).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/jira-fetch`:

```bash
#!/usr/bin/env bash
set -e

issue_key="${1?}"

response="$(curl --fail --silent --show-error \
  --user "${JIRA_EMAIL?}:${JIRA_API_TOKEN?}" \
  --url "${JIRA_BASE_URL?}/rest/api/3/issue/${issue_key}?expand=renderedFields&fields=summary")"

summary="$(jq --raw-output '.fields.summary' <<< "${response}")"
description="$(jq --raw-output '.renderedFields.description // ""' <<< "${response}")"

cat <<PROMPT
Implement the task described in the following Jira issue (${issue_key}).
Follow the repository's CLAUDE.md. Make the minimal change that satisfies the
issue. Do not modify unrelated code.

# ${summary}

${description}
PROMPT
```

- [ ] **Step 4: Make it executable**

Run: `chmod +x scripts/jira-fetch`

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_jira_fetch.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/jira-fetch tests/test_jira_fetch.py
git commit -m "feat(jira-agent): add jira-fetch script (issue -> prompt via renderedFields)"
```

---

## Task 2: `scripts/jira-transition`

**Files:**
- Create: `scripts/jira-transition`
- Test: `tests/test_jira_transition.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_jira_transition.py`:

```python
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "jira-transition"

captured: dict = {}

TRANSITIONS = {
    "transitions": [
        {"id": "11", "name": "To Do"},
        {"id": "31", "name": "In Review"},
    ]
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        captured["get_path"] = self.path
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(TRANSITIONS).encode())

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        captured["post_path"] = self.path
        captured["post_body"] = json.loads(self.rfile.read(length))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):  # silence server logging
        pass


def test_jira_transition_resolves_name_and_posts_id():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    result = subprocess.run(
        [str(SCRIPT), "PROJ-1", "in review"],  # lowercase -> case-insensitive match
        env={
            **os.environ,
            "JIRA_BASE_URL": f"http://127.0.0.1:{port}",
            "JIRA_EMAIL": "bot@example.com",
            "JIRA_API_TOKEN": "secret-token",
        },
        capture_output=True,
        text=True,
    )
    server.shutdown()

    assert result.returncode == 0, result.stderr
    assert captured["get_path"] == "/rest/api/3/issue/PROJ-1/transitions"
    assert captured["post_path"] == "/rest/api/3/issue/PROJ-1/transitions"
    assert captured["post_body"] == {"transition": {"id": "31"}}


def test_jira_transition_unknown_name_fails():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    result = subprocess.run(
        [str(SCRIPT), "PROJ-1", "Nonexistent"],
        env={
            **os.environ,
            "JIRA_BASE_URL": f"http://127.0.0.1:{port}",
            "JIRA_EMAIL": "bot@example.com",
            "JIRA_API_TOKEN": "secret-token",
        },
        capture_output=True,
        text=True,
    )
    server.shutdown()

    assert result.returncode != 0
    assert "Transition not found" in result.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_jira_transition.py -v`
Expected: FAIL — script não existe.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/jira-transition`:

```bash
#!/usr/bin/env bash
set -e

issue_key="${1?}"
transition_name="${2?}"

transitions="$(curl --fail --silent --show-error \
  --user "${JIRA_EMAIL?}:${JIRA_API_TOKEN?}" \
  --url "${JIRA_BASE_URL?}/rest/api/3/issue/${issue_key}/transitions")"

transition_id="$(jq --raw-output --arg name "${transition_name}" \
  '.transitions[] | select((.name | ascii_downcase) == ($name | ascii_downcase)) | .id' \
  <<< "${transitions}")"

if [[ -z "${transition_id}" ]]; then
  echo "Transition not found: ${transition_name}" >&2
  exit 1
fi

payload="$(jq --null-input --arg id "${transition_id}" '{transition: {id: $id}}')"

curl --fail --silent --show-error \
  --request POST \
  --user "${JIRA_EMAIL?}:${JIRA_API_TOKEN?}" \
  --header "Content-Type: application/json" \
  --url "${JIRA_BASE_URL?}/rest/api/3/issue/${issue_key}/transitions" \
  --data "${payload}"
```

- [ ] **Step 4: Make it executable**

Run: `chmod +x scripts/jira-transition`

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_jira_transition.py -v`
Expected: PASS (ambos os testes).

- [ ] **Step 6: Commit**

```bash
git add scripts/jira-transition tests/test_jira_transition.py
git commit -m "feat(jira-agent): add jira-transition script (resolve by name + POST)"
```

---

## Task 3: `scripts/ensure-pr`

Glue de GitHub (precisa de `gh` + repo real) — não tem unit test; é exercido pelo e2e (Task 6).

**Files:**
- Create: `scripts/ensure-pr`

- [ ] **Step 1: Write the implementation**

Create `scripts/ensure-pr`:

```bash
#!/usr/bin/env bash
set -e

branch="${1?}"
issue_key="${2?}"

url="$(gh pr list --head "${branch}" --json url --jq '.[0].url // ""')"
if [[ -z "${url}" ]]; then
  url="$(gh pr create \
    --head "${branch}" \
    --base main \
    --title "${issue_key}: agent implementation" \
    --body "Automated by jira-agent. Jira: ${JIRA_BASE_URL?}/browse/${issue_key}")"
fi

echo "${url}"
```

Notas:
- `gh pr create` imprime a URL do PR em stdout — capturada direto.
- O título começa com a issue key, o que faz a app GitHub for Jira linkar o PR ao dev panel da issue.
- `GH_TOKEN` (token da App, output da action) e `JIRA_BASE_URL` vêm do ambiente do step (Task 4).

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/ensure-pr`

- [ ] **Step 3: Validate bash syntax**

Run: `bash -n scripts/ensure-pr`
Expected: sem saída, returncode 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/ensure-pr
git commit -m "feat(jira-agent): add ensure-pr script (find-or-create PR, print URL)"
```

---

## Task 4: Wire `jira-agent.yaml`

**Files:**
- Modify: `.github/workflows/jira-agent.yaml`

- [ ] **Step 1: Rewrite the workflow**

Replace the entire content of `.github/workflows/jira-agent.yaml` with:

```yaml
name: jira-agent

on:
  repository_dispatch:
    types: [jira-trigger-event]
  workflow_dispatch:
    inputs:
      jira_issue:
        description: "Jira issue key (ex: PROJ-123)"
        required: true
        type: string

jobs:
  run:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      id-token: write
    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Read issue key
        env:
          ISSUE_KEY_RAW: ${{ github.event.client_payload.issue_key || inputs.jira_issue }}
        run: |
          if [[ ! "${ISSUE_KEY_RAW}" =~ ^[A-Z]+-[0-9]+$ ]]; then
            echo "Invalid issue key: ${ISSUE_KEY_RAW}" >&2
            exit 1
          fi
          echo "ISSUE_KEY=${ISSUE_KEY_RAW}" >> "$GITHUB_ENV"

      - name: Build prompt
        env:
          JIRA_BASE_URL: ${{ secrets.JIRA_BASE_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          delimiter="EOF_$(openssl rand -hex 16)"
          {
            echo "AGENT_PROMPT<<${delimiter}"
            scripts/jira-fetch "${ISSUE_KEY}"
            echo "${delimiter}"
          } >> "$GITHUB_ENV"

      - name: Implement with Claude
        id: claude
        uses: anthropics/claude-code-action@v1
        with:
          prompt: ${{ env.AGENT_PROMPT }}
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          claude_args: "--model claude-opus-4-8"

      - name: Ensure PR and capture URL
        id: pr
        env:
          GH_TOKEN: ${{ steps.claude.outputs.github_token }}
          JIRA_BASE_URL: ${{ secrets.JIRA_BASE_URL }}
        run: |
          pr_url="$(scripts/ensure-pr "${{ steps.claude.outputs.branch_name }}" "${ISSUE_KEY}")"
          echo "url=${pr_url}" >> "$GITHUB_OUTPUT"

      - name: Comment + transition on Jira
        env:
          JIRA_BASE_URL: ${{ secrets.JIRA_BASE_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          scripts/jira-comment "${ISSUE_KEY}" "Agent opened a PR: ${{ steps.pr.outputs.url }}"
          scripts/jira-transition "${ISSUE_KEY}" "In Review"
```

> **Segurança:** `github.event.client_payload.*` é input não-confiável (atacante controla o
> dispatch). O valor é vinculado a `ISSUE_KEY_RAW` via `env` e validado por regex
> (`^[A-Z]+-[0-9]+$`) antes de virar `ISSUE_KEY` — nunca interpolado direto num `run:`.
> O prompt é passado via heredoc no `GITHUB_ENV` com delimitador aleatório (`openssl rand`)
> para não quebrar nem permitir injeção a partir do conteúdo (não-confiável) da issue.

> **`permissions.id-token: write`** está incluído por precaução (a action pode usá-lo na troca
> do OAuth token). Se o e2e (Task 6) mostrar que não é necessário, remover. `contents` e
> `pull-requests: write` são exigidos pelo `ensure-pr`/criação de branch.

- [ ] **Step 2: Validate the YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/jira-agent.yaml'))"`
Expected: sem saída, returncode 0.

- [ ] **Step 3: Confirm full suite still green**

Run: `make test`
Expected: PASS, coverage permanece 100% (sem código Python de produção novo).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/jira-agent.yaml
git commit -m "feat(jira-agent): implement real pipeline (claude-code-action + PR + Jira)"
```

---

## Task 5: Rewrite the runbook

**Files:**
- Rewrite: `docs/runbooks/jira-coding-agent-setup.md`

- [ ] **Step 1: Rewrite the runbook**

Replace the entire content of `docs/runbooks/jira-coding-agent-setup.md` with:

````markdown
# Jira Coding Agent — Setup (v2)

Passo a passo para o agente real: disparar a partir do Jira, implementar via
`claude-code-action`, abrir um PR e devolver a URL ao Jira transicionando a issue
para "In Review". Specs: `docs/sdlc/02-design/2026-06-13-jira-coding-agent.md` (v1) e
`docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md` (v2).

## Lado GitHub

1. **App "Claude"** — confirmar a app oficial da Anthropic instalada no repo
   (https://github.com/apps/claude → Configure → o repo `wasp-agent` deve aparecer).
   Ela fornece o token de operações de git/PR internamente; **não há PAT**.
2. **OAuth token** — gerar localmente com `claude setup-token` (conta com assinatura
   Pro/Max) e adicionar como secret `CLAUDE_CODE_OAUTH_TOKEN`
   (Settings → Secrets and variables → Actions).
3. **Secrets do Jira** (mantidos da v1):
   - `JIRA_BASE_URL` — ex: `https://smsilva.atlassian.net`
   - `JIRA_EMAIL` — e-mail da conta de serviço do Jira
   - `JIRA_API_TOKEN` — token de API do Jira
4. **Branch default** — `jira-agent.yaml` precisa estar no branch default
   (`repository_dispatch` só dispara a partir dele).

## Lado Jira

1. **Automation rule** (inalterada da v1) — Project settings → Automation:
   - **Trigger:** "Manual trigger from work item" (ou atribuição/transição).
   - **Action:** "Send web request":
     - URL: `https://api.github.com/repos/smsilva/wasp-agent/dispatches`
       (precisa do prefixo `api.github.com/repos/` — sem ele, 404)
     - Method: `POST`
     - Headers:
       - `Authorization: Bearer <TRIGGER_TOKEN>` (PAT fine-grained, `Contents: write` +
         `Actions: write`, guardado **no Jira**)
       - `Accept: application/vnd.github+json`
     - Content-Type: `application/json`
     - Body (Custom data):
       ```json
       {
         "event_type": "jira-trigger-event",
         "client_payload": { "issue_key": "{{issue.key}}" }
       }
       ```
2. **Transição "In Review"** — garantir que o status "In Review" existe no workflow do
   projeto e é alcançável a partir do status atual da issue (o `jira-transition` resolve o
   id por nome).
3. **(Opcional) App GitHub for Jira** — instalar `marketplace.atlassian.com` → "GitHub for
   Atlassian" no site `smsilva.atlassian.net` para o dev panel. Como o título do PR começa
   com a issue key, o PR aparece linkado na issue. Complemento de visibilidade; não substitui
   os scripts (ver spec v2 §10).

## Validação

1. Disparar uma issue de teste (PLTF-11) via menu `• • •` → Automation, ou rodar o workflow
   manualmente em Actions → `jira-agent` → Run workflow (input `jira_issue`).
2. Conferir, no run de `jira-agent`:
   - `Implement with Claude` verde, com `branch_name` no output;
   - `Ensure PR and capture URL` produzindo uma URL.
3. No GitHub: PR aberto como `claude[bot]` com diff real; `ci.yaml` rodando no PR.
4. No Jira: comentário "Agent opened a PR: …" e issue em "In Review".

## Troubleshooting

- **404 no dispatch:** URL sem `api.github.com/repos/`, ou repo/owner errado.
- **401/403 no dispatch:** trigger token sem `Contents: write`/`Actions: write` ou expirado.
- **Workflow não dispara:** `jira-agent.yaml` não está no branch default, ou `event_type`
  não bate com `types: [jira-trigger-event]`.
- **`Implement with Claude` falha de auth:** `CLAUDE_CODE_OAUTH_TOKEN` ausente/expirado
  (regerar com `claude setup-token`), ou app "Claude" não instalada no repo.
- **`ensure-pr` sem PR / branch vazio:** a action não produziu mudanças (issue ambígua —
  tratada em v3) ou não pushou o branch; conferir o log da action.
- **`jira-transition` falha "Transition not found":** o status "In Review" não existe ou não
  é alcançável a partir do status atual da issue.
````

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/jira-coding-agent-setup.md
git commit -m "docs(runbooks): rewrite Jira coding agent setup for v2"
```

---

## Task 6: Empirical e2e validation (manual)

Não há mocking de Jira+GitHub+Claude juntos — a validação real é manual e também **confirma**
o comportamento da `claude-code-action` em automation mode (ponto subdocumentado).

- [ ] **Step 1: Push the branch and merge to default**

`repository_dispatch`/`workflow_dispatch` só enxergam o workflow no branch default. Abrir PR
desta branch para `main`, mergear, e então validar a partir do `main`.

- [ ] **Step 2: Trigger a real run against PLTF-11**

Via Jira (issue PLTF-11 → `• • •` → Automation) ou via Actions → `jira-agent` → Run workflow
com `jira_issue=PLTF-11`.

- [ ] **Step 3: Observe the action behavior and confirm assumptions**

No run, verificar:
- `steps.claude.outputs.branch_name` está preenchido (a action criou/pushou um branch).
- A action criou um PR sozinha (então `ensure-pr` apenas o encontra) **ou** não criou (então
  `ensure-pr` o cria). Ambos os caminhos são suportados — só registrar qual ocorreu.
- `id-token: write` foi necessário? Se o run passar sem erro relacionado a OIDC, manter; se a
  action acusar permissão faltante, ajustar.

Se `branch_name` vier vazio (a action não pushou em automation mode), ajustar a Task 4 para
instruir o push explicitamente no prompt e re-rodar.

- [ ] **Step 4: Confirm success criteria (spec §9)**

- Run verde na aba Actions.
- PR aberto como `claude[bot]` com diff real; `ci.yaml` rodando no PR.
- Comentário "Agent opened a PR: …" na issue PLTF-11.
- Issue PLTF-11 em "In Review".

- [ ] **Step 5: Record findings**

Registrar no `HANDOFF.md` (Task 7) o comportamento observado da action (auto-PR sim/não,
`id-token` necessário sim/não) para não re-investigar depois.

---

## Task 7: Update docs / state

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md` (Status → Implemented)
- Modify: `docs/sdlc/CLAUDE.md` (mover o par v2 design+execução para nota de implementado, se a convenção do projeto pedir arquivamento pós-merge)

- [ ] **Step 1: Mark the v2 design Implemented**

Em `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md`, mudar `**Status:** Approved`
para `**Status:** Implemented`.

- [ ] **Step 2: Update HANDOFF.md**

Atualizar a seção de estado: v2 entregue e validada (com o comportamento observado da action,
da Task 6 Step 5). Atualizar o item de Backlog "Jira Coding Agent v2/v3" para remover v2 e
manter apenas v3.

- [ ] **Step 3: Commit**

```bash
git add HANDOFF.md docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md docs/sdlc/CLAUDE.md
git commit -m "docs: record Jira coding agent v2 as implemented"
```

---

## Verificação final

```bash
make format
make test
make e2e-with-debug
```

- `make test` deve reportar 100% coverage (sem código Python de produção novo; só test files
  e bash scripts).
- A validação end-to-end real do agente é a Task 6 (manual) — `make e2e-with-debug` cobre o
  fluxo principal do `wasp-agent`, não o `jira-agent.yaml`.

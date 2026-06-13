# Jira Coding Agent (walking skeleton v1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provar o round-trip Jira → GitHub → Jira: uma issue atribuída/transicionada dispara um workflow que devolve um comentário com o link do run.

**Architecture:** Jira Automation faz `repository_dispatch` no GitHub. O workflow `jira-agent.yaml` é um skeleton com um step por etapa do pipeline alvo — todas as etapas futuras só logam "would …", e apenas a leitura do `issue_key` e o comentário de volta no Jira são reais. O comentário usa `scripts/jira-comment` (bash + curl + jq), sem lógica inline no YAML.

**Tech Stack:** GitHub Actions (`repository_dispatch`), bash, curl, jq, Jira Cloud REST API v3 (comment endpoint, payload ADF), pytest (teste do script via mock HTTP server).

**Spec:** `docs/sdlc/02-design/2026-06-13-jira-coding-agent.md`

---

## File Structure

- **Create** `scripts/jira-comment` — executável bash: recebe `issue_key` + texto, monta payload ADF com `jq`, faz `POST` no endpoint de comentário do Jira (basic auth via env).
- **Create** `tests/test_jira_comment.py` — roda o script contra um mock HTTP server local e valida método, path, header de auth e corpo ADF.
- **Create** `.github/workflows/jira-agent.yaml` — workflow `repository_dispatch`; skeleton de steps (stubs que logam) + comentário real no Jira.
- **Create** `docs/runbooks/jira-coding-agent-setup.md` — passo a passo reproduzível (lado Jira, lado GitHub, validação, troubleshooting).
- **Modify** `HANDOFF.md` — registrar o estado atual (v1 entregue, v2/v3 deferred).

Convenção de bash do projeto (regras globais): sem extensão no executável, long-form CLI options, 2-space indent, locais minúsculos, sempre aspas em `"${var}"`, args obrigatórios via `${var?}`, `set -e` para sequência.

---

## Task 1: `scripts/jira-comment`

**Files:**
- Create: `scripts/jira-comment`
- Test: `tests/test_jira_comment.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_jira_comment.py`:

```python
import base64
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "jira-comment"

captured: dict = {}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        captured["path"] = self.path
        captured["auth"] = self.headers["Authorization"]
        captured["body"] = json.loads(self.rfile.read(length))
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):  # silence server logging
        pass


def test_jira_comment_posts_adf_comment():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.handle_request, daemon=True).start()

    result = subprocess.run(
        [str(SCRIPT), "PROJ-1", "Agent picked this up. Run: http://x/123"],
        env={
            **os.environ,  # herda PATH para achar bash/curl/jq
            "JIRA_BASE_URL": f"http://127.0.0.1:{port}",
            "JIRA_EMAIL": "bot@example.com",
            "JIRA_API_TOKEN": "secret-token",
        },
        capture_output=True,
        text=True,
    )
    server.server_close()

    assert result.returncode == 0, result.stderr
    assert captured["path"] == "/rest/api/3/issue/PROJ-1/comment"
    expected_auth = base64.b64encode(b"bot@example.com:secret-token").decode()
    assert captured["auth"] == f"Basic {expected_auth}"
    text = captured["body"]["body"]["content"][0]["content"][0]["text"]
    assert text == "Agent picked this up. Run: http://x/123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_jira_comment.py -v`
Expected: FAIL — script não existe (`No such file or directory` / returncode != 0).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/jira-comment`:

```bash
#!/usr/bin/env bash
set -e

issue_key="${1?}"
comment_body="${2?}"

payload="$(jq --null-input --arg text "${comment_body}" \
  '{body: {type: "doc", version: 1, content: [{type: "paragraph", content: [{type: "text", text: $text}]}]}}')"

curl --fail --silent --show-error \
  --request POST \
  --user "${JIRA_EMAIL?}:${JIRA_API_TOKEN?}" \
  --header "Content-Type: application/json" \
  --url "${JIRA_BASE_URL?}/rest/api/3/issue/${issue_key}/comment" \
  --data "${payload}"
```

- [ ] **Step 4: Make it executable**

Run: `chmod +x scripts/jira-comment`

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_jira_comment.py -v`
Expected: PASS.

- [ ] **Step 6: Confirm full suite still green**

Run: `make test`
Expected: PASS, coverage permanece 100% (sem novo código Python de produção).

- [ ] **Step 7: Commit**

```bash
git add scripts/jira-comment tests/test_jira_comment.py
git commit -m "feat(jira-agent): add jira-comment script with ADF payload"
```

---

## Task 2: `jira-agent.yaml` workflow skeleton

**Files:**
- Create: `.github/workflows/jira-agent.yaml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/jira-agent.yaml`:

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
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Read issue key
        env:
          ISSUE_KEY_RAW: ${{ github.event.client_payload.issue_key || inputs.jira_issue }}
        run: |
          if [[ ! "${ISSUE_KEY_RAW}" =~ ^[A-Z]+-[0-9]+$ ]]; then
            echo "Invalid issue key: ${ISSUE_KEY_RAW}" >&2
            exit 1
          fi
          echo "ISSUE_KEY=${ISSUE_KEY_RAW}" >> "$GITHUB_ENV"

      - name: Fetch issue (stub)
        run: echo "would fetch issue details for ${ISSUE_KEY}"

      - name: Create branch (stub)
        run: echo "would create branch agent/${ISSUE_KEY}-<slug>"

      - name: Implement with claude (stub)
        run: echo "would run claude -p to implement ${ISSUE_KEY}"

      - name: Commit and push (stub)
        run: echo "would commit and push"

      - name: Open PR (stub)
        run: echo "would open PR for ${ISSUE_KEY}"

      - name: Comment back on Jira
        env:
          JIRA_BASE_URL: ${{ secrets.JIRA_BASE_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          scripts/jira-comment "${ISSUE_KEY}" \
            "Agent picked this up. Run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

> **Segurança:** `github.event.client_payload.*` é input não-confiável (atacante controla o
> dispatch). Nunca interpolar direto num `run:` — é injeção de comando. O valor é vinculado a
> `ISSUE_KEY_RAW` via `env` e validado por regex (`^[A-Z]+-[0-9]+$`) antes de virar `ISSUE_KEY`.
> `github.server_url`/`repository`/`run_id` vêm do contexto do GitHub (confiáveis).

- [ ] **Step 2: Validate the YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/jira-agent.yaml'))"`
Expected: sem saída e returncode 0 (YAML válido).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/jira-agent.yaml
git commit -m "feat(jira-agent): add repository_dispatch workflow skeleton"
```

---

## Task 3: Runbook reproduzível

**Files:**
- Create: `docs/runbooks/jira-coding-agent-setup.md`

- [ ] **Step 1: Write the runbook**

Create `docs/runbooks/jira-coding-agent-setup.md`:

````markdown
# Jira Coding Agent — Setup (v1)

Passo a passo para disparar o `jira-agent.yaml` a partir do Jira e receber o
comentário de volta. Spec: `docs/sdlc/02-design/2026-06-13-jira-coding-agent.md`.

## Lado GitHub

1. **Trigger token** — criar um PAT fine-grained com permissão `Contents: write`
   no repositório `wasp-agent` (ver `docs/runbooks/github-pat-setup.md` para o
   passo a passo de criação). Guardar o valor para colar no Jira (passo do Jira #2).
2. **Secrets do repo** (Settings → Secrets and variables → Actions):
   - `JIRA_BASE_URL` — ex: `https://suaempresa.atlassian.net`
   - `JIRA_EMAIL` — e-mail da conta de serviço do Jira
   - `JIRA_API_TOKEN` — token de API do Jira (próximo passo)
3. **Branch default** — garantir que `jira-agent.yaml` está mergeado no branch
   default; `repository_dispatch` só dispara o workflow a partir dele.

## Lado Jira

1. **API token** — criar em https://id.atlassian.com/manage-profile/security/api-tokens
   com a conta de serviço; usar no secret `JIRA_API_TOKEN`.
2. **Automation rule** (Project settings → Automation → Create rule):
   - **Trigger:** issue atribuída ao agente (ou transição para "Ready for Agent").
   - **Action:** "Send web request":
     - URL: `https://api.github.com/repos/<owner>/wasp-agent/dispatches`
       (precisa do prefixo `api.github.com/repos/` — sem ele, 404)
     - Method: `POST`
     - Headers:
       - `Authorization: Bearer <TRIGGER_TOKEN>`  (token do GitHub, passo GitHub #1)
       - `Accept: application/vnd.github+json`
     - Content-Type: `application/json`
     - Body (Custom data):
       ```json
       {
         "event_type": "jira-trigger-event",
         "client_payload": { "issue_key": "{{issue.key}}" }
       }
       ```

## Validação

1. Atribuir/transicionar uma issue de teste no Jira.
2. Conferir o run em GitHub → aba **Actions** → workflow `jira-agent`.
3. Conferir o comentário "Agent picked this up. Run: …" na issue do Jira.

## Troubleshooting

- **404 no dispatch:** URL sem `api.github.com/repos/`, ou repo/owner errado.
- **401/403 no dispatch:** trigger token sem `Contents: write` ou expirado.
- **Workflow não dispara:** `jira-agent.yaml` não está no branch default, ou o
  `event_type` no payload não bate com `types: [jira-trigger-event]`.
- **Falha no step "Comment back on Jira":** `JIRA_BASE_URL` com barra final, e-mail/token
  inválidos, ou a issue key não existe.
````

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/jira-coding-agent-setup.md
git commit -m "docs(runbooks): add Jira coding agent setup guide (v1)"
```

---

## Task 4: Atualizar HANDOFF.md

**Files:**
- Modify: `HANDOFF.md`

- [ ] **Step 1: Read current HANDOFF**

Run: `cat HANDOFF.md`
Objetivo: encontrar a seção de estado atual / backlog para inserir a entrada.

- [ ] **Step 2: Add an entry**

Adicionar uma linha registrando: "Jira Coding Agent v1 (walking skeleton) entregue —
`repository_dispatch` → comentário de volta no Jira. v2 (implementação real com `claude -p`,
GitHub App, PR) e v3 (gate de ambiguidade, `pr-agent.yaml` de CI, dry-run) Deferred. Spec:
`docs/sdlc/02-design/2026-06-13-jira-coding-agent.md`."

(Seguir o formato/seção existente do `HANDOFF.md`; não reformatar o resto.)

- [ ] **Step 3: Commit**

```bash
git add HANDOFF.md
git commit -m "docs: record Jira coding agent v1 in HANDOFF"
```

---

## Verificação final (manual)

A validação end-to-end real é manual (não há mocking de Jira+GitHub juntos): seguir
`docs/runbooks/jira-coding-agent-setup.md` → seção "Validação". Critério de sucesso (spec §7):
o run aparece na aba Actions, termina verde, e a issue recebe o comentário com o link do run.

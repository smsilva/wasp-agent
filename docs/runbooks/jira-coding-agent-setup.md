# Jira Coding Agent — Setup (v1)

Passo a passo para disparar o `jira-agent.yaml` a partir do Jira e receber o
comentário de volta. Spec: `docs/sdlc/02-design/2026-06-13-jira-coding-agent.md`.

## Execução manual (primeiro teste, sem Jira)

O workflow também aceita `workflow_dispatch`, então dá para validar a execução antes de
configurar o Jira. Basta os secrets `JIRA_*` (passos GitHub #2 abaixo) já estarem no repo.

1. GitHub → aba **Actions** → workflow **jira-agent** → **Run workflow**.
2. Informar a issue key em `jira_issue` (ex: `PROJ-123`, formato `^[A-Z]+-[0-9]+$`).
3. Conferir o run e o comentário na issue do Jira.

O resto deste runbook cobre o disparo automático a partir do Jira.

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
   com a conta de serviço; usar no secret `JIRA_API_TOKEN`. Use **"Create API token"**
   (sem scopes) — o `scripts/jira-comment` usa basic auth clássico (`email:token`).
   Antes de salvar no GitHub, validar o token:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" \
     -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
     "$JIRA_BASE_URL/rest/api/3/myself"   # espera HTTP 200
   ```
2. **Automation rule** (Project settings → Automation → Create rule). A UI é um
   builder: adiciona-se um **Trigger** e depois um step **Action**.

   **Trigger** — opções (escolher uma):
   - **Manual trigger from work item** — recomendado para o primeiro teste: roda
     sob demanda pelo menu da issue, com `{{issue.key}}` real no payload. Sem
     disparo acidental. Defaults servem (groups: All logged in users; work type:
     All work types; deixar "Prompt for input" desmarcado).
   - **Work item transitioned** — para um status tipo "Ready for Agent".
   - **Work item assigned** — fluxo de atribuição; cuidar para não disparar em toda
     atribuição (adicionar condição pelo assignee).

   **Action: Send web request**
   - **Web request URL:** `https://api.github.com/repos/<owner>/wasp-agent/dispatches`
     (precisa do prefixo `api.github.com/repos/` — sem ele, 404)
   - **HTTP method:** `POST`
   - **Headers (optional):** adicionar dois —
     - `Authorization` = `Bearer <TRIGGER_TOKEN>` (token do GitHub, passo GitHub #1).
       Marcar a coluna **Hidden** nessa linha para não vazar o token nos logs.
     - `Accept` = `application/vnd.github+json`
   - **Web request body:** trocar de `Empty` para **`Custom data`** e colar:
     ```json
     {
       "event_type": "jira-trigger-event",
       "client_payload": { "issue_key": "{{issue.key}}" }
     }
     ```
   - **Não usar o botão "Validate"** do Send web request: a validação roda sem
     contexto de issue, então `{{issue.key}}` vai vazio/literal e o step
     "Read issue key" do workflow falha no regex. Validar disparando de uma issue real.

   Salvar com **Save and enable** → **Turn on flow** (definir nome e visibilidade;
   `Private` basta).

3. **Disparar (Manual trigger):** abrir uma issue → menu **• • •** (More actions) →
   **Automation** / nome da regra → executar.

## Validação

1. Disparar a regra de uma issue de teste (Manual trigger: menu **• • •** →
   Automation; ou atribuir/transicionar, conforme o trigger escolhido).
2. Conferir o run em GitHub → aba **Actions** → workflow `jira-agent`
   (evento `repository_dispatch`).
3. Conferir o comentário "Agent picked this up. Run: …" na issue do Jira.

Validação só do lado GitHub, sem o Jira (útil para isolar o pipeline):
```bash
gh api repos/<owner>/wasp-agent/dispatches -X POST \
  -f event_type=jira-trigger-event \
  -F client_payload[issue_key]=PLTF-11
```

## Troubleshooting

- **404 no dispatch:** URL sem `api.github.com/repos/`, ou repo/owner errado.
- **401/403 no dispatch:** trigger token sem `Contents: write` ou expirado.
- **Workflow não dispara:** `jira-agent.yaml` não está no branch default, ou o
  `event_type` no payload não bate com `types: [jira-trigger-event]`.
- **Falha no step "Comment back on Jira":** `JIRA_BASE_URL` com barra final, e-mail/token
  inválidos, ou a issue key não existe.
- **Job falha em "Read issue key" (Invalid issue key):** o workflow valida a key contra
  `^[A-Z]+-[0-9]+$`; confirme que `{{issue.key}}` está sendo enviado e tem o formato `PROJ-123`.
  Causa comum: usar o botão **"Validate"** do Send web request (roda sem contexto de
  issue, manda `{{issue.key}}` literal/vazio). Dispare de uma issue real.
- **Run aparece mas no branch errado:** `repository_dispatch` sempre roda a partir do
  branch default (`main`). Mudanças no workflow só valem após merge no default.

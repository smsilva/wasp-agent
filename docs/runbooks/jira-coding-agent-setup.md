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
- **Job falha em "Read issue key" (Invalid issue key):** o workflow valida a key contra
  `^[A-Z]+-[0-9]+$`; confirme que `{{issue.key}}` está sendo enviado e tem o formato `PROJ-123`.

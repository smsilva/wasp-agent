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
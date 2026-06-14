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
5. **Workflow permissions** — Settings → Actions → General → Workflow permissions:
   - Marcar **"Allow GitHub Actions to create and approve pull requests"**.
   - Sem isso, `gh pr create` retorna `GraphQL: GitHub Actions is not permitted to
     create or approve pull requests (createPullRequest)`. O `GITHUB_TOKEN` é
     bloqueado por default para criar PRs; este flag libera (escopo: apenas o
     próprio workflow, governado pelas `permissions:` declaradas no job).
   - PRs aparecem como autorados por `github-actions[bot]`; o commit no branch
     `claude/<ISSUE_KEY>` mantém autoria `claude[bot]`.

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

Validado end-to-end em 2026-06-13 com a issue PLTF-11 (run `27483606376`, PR `#9`).

1. Disparar uma issue de teste (PLTF-11) via menu `• • •` → Automation, ou rodar o workflow
   manualmente em Actions → `jira-agent` → Run workflow (input `jira_issue`).
2. Conferir, no run de `jira-agent`:
   - `Implement with Claude` verde — em `prompt` mode os outputs `branch_name` e
     `github_token` ficam vazios (a action retorna `github_token` só quando há um
     installation event do app, o que não acontece aqui). O `BRANCH_NAME` é
     hard-coded em `claude/${ISSUE_KEY}` no workflow.
   - `Ensure PR and capture URL` produzindo uma URL.
   - `Upload Claude execution log` anexando `claude-execution-log-<ISSUE_KEY>.tar.gz`
     (artefato com retenção de 30 dias; útil para post-mortem).
3. No GitHub: PR aberto como `github-actions[bot]` com diff real; commit no branch
   ainda atribuído a `claude[bot]`; `ci.yaml` rodando no PR.
   - **Primeiro PR do bot exige aprovação manual de workflow.** O GitHub bloqueia
     a primeira execução de workflows em PRs autorados por `github-actions[bot]`
     (ou qualquer first-time contributor) e mostra "1 workflow awaiting approval"
     no PR. Clicar em **Approve workflows to run** uma vez. PRs subsequentes do
     bot devem rodar sem aprovação. Para automatizar, ajustar Settings → Actions
     → General → "Fork pull request workflows from outside collaborators".
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
- **`ensure-pr` falha com `gh: HTTP 401 Bad credentials`:** o env `GH_TOKEN` está vinculado
  a `steps.claude.outputs.github_token`, que é vazio em `prompt` mode. Usar
  `secrets.GITHUB_TOKEN` (já é o estado atual do workflow desde PR #8).
- **`ensure-pr` falha com `GraphQL: GitHub Actions is not permitted to create or approve
  pull requests`:** o flag "Allow GitHub Actions to create and approve pull requests" está
  desligado em Settings → Actions → General → Workflow permissions. Marcar (ver §5 acima).
- **PR aberto mas CI não roda ("1 workflow awaiting approval"):** primeiro PR do bot
  exige aprovação manual. Abrir o PR, clicar em **Approve workflows to run**. Recorrente
  apenas em PRs subsequentes se a política do repo bloquear contributors externos —
  ajustar em Settings → Actions → General → "Fork pull request workflows from outside
  collaborators".
- **`jira-transition` falha "Transition not found":** o status "In Review" não existe ou não
  é alcançável a partir do status atual da issue.

## Decisões de design observadas em runtime

- **`--dangerously-skip-permissions`** (não `--allowed-tools`): o gate de permissão da action
  é word-by-word e rejeita composites (`command -v uv`, `bash -lc '...'`, `make test`). A
  fronteira de segurança real é o runner ephemeral + `permissions:` do job + OAuth token
  scopado ao repo + output é PR (não merge). Ver SEC-007 (resolved).
- **Branch hard-coded**: `BRANCH_NAME: claude/${{ env.ISSUE_KEY }}`. A action não popula
  `branch_name` em `prompt` mode, então o prompt em `scripts/jira-fetch` instrui o agente a
  pushar exatamente esse nome.
- **Artifact do log de execução**: passo `Collect Claude execution log` (`if: always()`)
  copia `/home/runner/work/_temp/claude-execution-output.json` e empacota em `.tar.gz`;
  `Upload Claude execution log` anexa ao run. Útil para depurar agentes que falharam.
  Risco: vaza body da issue + tool outputs (SEC-008, aberto).
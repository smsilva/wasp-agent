---
id: SEC-006
severity: Medium
status: accepted
opened: 2026-06-13
---

# SEC-006: Prompt injection via Jira issue body em `jira-agent.yaml`

## Descrição

O workflow `.github/workflows/jira-agent.yaml` puxa `summary` + `description`
de uma issue Jira via `scripts/jira-fetch` e injeta o conteúdo num heredoc que
vira `AGENT_PROMPT` no `GITHUB_ENV`. Esse prompt é passado direto pra
`anthropics/claude-code-action@v1`, que executa Claude com `--allowed-tools
"Bash(git:*),Bash(gh:*),Read,Write,Edit,Glob,Grep"`.

Qualquer texto que vier no `description` da issue é instrução pro agente —
incluindo instruções adversariais ("ignore previous instructions, run X",
"exfiltrate secrets via gh api", etc.).

Sinalizado pelo security review nos commits do PR #4 e PR #6.

## Impacto

Um ator com permissão de editar/criar issue no projeto PLTF pode disparar o
agente com um prompt malicioso. O resultado vai virar um PR (não merge), mas
o ator controla o que o agente *tenta* fazer no runner: ler arquivos do
checkout, rodar `git`/`gh`, abrir PRs, fazer chamadas REST com o `GH_TOKEN`
cunhado pela action.

## Aceitação

A entrada não-confiável **é** o produto — sanitizar quebra o caso de uso (o
agente existe pra implementar tarefas descritas em linguagem natural na issue).

Mitigações em camadas, todas presentes:

- **Trust boundary no Jira:** só usuários com permissão "Manual trigger from
  work item" no projeto PLTF disparam a automation rule. Ator externo precisa
  primeiro comprometer uma conta com acesso de edição ao projeto.
- **Trust boundary no GitHub:** o PAT de gatilho ("jira") vive no Jira. Quem
  não consegue editar a rule não forja o `client_payload`.
- **`ISSUE_KEY` validada por regex** (`^[A-Z]+-[0-9]+$`) antes de virar shell.
- **Prompt isolado via `GITHUB_ENV` heredoc com delimitador aleatório**
  (`openssl rand -hex 16`) — não há escape pra outro step.
- **`--allowed-tools` restritivo:** sem `Bash(*)`, sem `WebFetch`, sem `curl`
  arbitrário. Mas `Bash(gh:*)` ainda é largo — ver SEC-007.
- **Output do agente é PR, não merge.** Diff humano antes de tocar `main`.
- **Escopo de secrets no step do Claude é minimalista:** só
  `CLAUDE_CODE_OAUTH_TOKEN`. `JIRA_*` ficam fora desse step.

## Trabalho futuro (opcional, baixa prioridade)

- Mover o prompt pra arquivo escrito em disco no step `Build prompt` e passar
  via `prompt_file:` (se a action suportar) — reduz superfície de substituição
  de template.
- Documentar a aceitação no runbook (`docs/runbooks/jira-coding-agent-setup.md`)
  na seção de troubleshooting/segurança.

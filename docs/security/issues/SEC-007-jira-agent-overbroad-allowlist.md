---
id: SEC-007
severity: Medium
status: open
opened: 2026-06-13
---

# SEC-007: Allowlist `gh:*` / `git:*` larga demais em `jira-agent.yaml`

## Descrição

PR #6 adicionou `--allowed-tools "Bash(git:*),Bash(gh:*),Read,Write,Edit,Glob,Grep"`
ao step `Implement with Claude` em `.github/workflows/jira-agent.yaml` pra
desbloquear `git branch/commit/push` (fix do `permission_denials_count: 3`
observado no run 27479964934).

O fluxo do workflow só usa, na prática:
- `git config user.email/user.name`
- `git checkout -b claude/<KEY>`
- `git add -A && git commit -m ...`
- `git push --set-upstream origin claude/<KEY>`
- `gh pr create` (no `scripts/ensure-pr`, NÃO no agente)
- `gh pr list` (no `scripts/ensure-pr`, NÃO no agente)

Mas o allowlist autoriza qualquer subcomando de `gh` e `git`. Combinado com
SEC-006 (entrada não-confiável da issue), isso amplifica o que um prompt
malicioso pode tentar.

Sinalizado pelo security review do push para `fix/jira-agent-allow-git-push`.

## Impacto

Com `Bash(gh:*)` o agente pode:

- `gh release create` / `gh release upload` — publicar artefato como
  `claude[bot]` num release.
- `gh workflow run` — disparar outros workflows (incluindo `jira-agent` em
  loop, gerando custos).
- `gh api` arbitrário em qualquer endpoint REST/GraphQL que o `GH_TOKEN`
  cunhado pela action tenha escopo (issues, labels, projects, etc.).
- `gh secret list` — enumerar nomes de secrets (não valores).

Com `Bash(git:*)`:

- `git config` / `git remote set-url` — manipular remote, mas o efeito é
  contido ao runner (efêmero).
- `git push` pra outros refs do mesmo repo — limitado pelo escopo do
  `GH_TOKEN`.

A consequência prática direta — escrita no repo — já está coberta pelo
princípio "PR-não-merge" do SEC-006. O risco real desta issue é exfiltração
ou disrupção via API do GitHub, não comprometimento de `main`.

## Fix proposto

Estreitar o allowlist pra exatamente o que o workflow precisa. Hipótese a
validar: a sintaxe `--allowed-tools` da `claude-code-action` aceita patterns
de múltiplos tokens (`Bash(git checkout:*)`, `Bash(gh pr:*)`)?

- **Se sim:** trocar pra `Bash(git config:*),Bash(git checkout:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Read,Write,Edit,Glob,Grep`
  e remover `Bash(gh:*)` por completo (o `gh pr create` já vive no `ensure-pr`,
  fora do agente).
- **Se não:** mover toda a operação `git` pro próprio `ensure-pr` (ou um
  `scripts/git-push-claude-branch`) e remover `Bash(git:*)` também. O agente
  fica só com `Read,Write,Edit,Glob,Grep`, e o workflow faz o push após o
  step do Claude.

A segunda opção é mais limpa porque tira a action do caminho crítico de
shell entirely.

## Trabalho

Investigar a sintaxe + implementar — fazer após validar funcionalmente que o
PR #6 desbloqueou o fluxo (run verde do PLTF-11). Iterar em segurança antes
da validação funcional arrisca confundir os sinais.

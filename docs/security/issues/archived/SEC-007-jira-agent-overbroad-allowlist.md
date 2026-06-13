---
id: SEC-007
severity: Medium
status: resolved
opened: 2026-06-13
resolved: 2026-06-13
---

# SEC-007: Allowlist `gh:*` / `git:*` larga demais em `jira-agent.yaml`

## Descrição

PR #6 adicionou `--allowed-tools "Bash(git:*),Bash(gh:*),Read,Write,Edit,Glob,Grep"`
ao step `Implement with Claude` em `.github/workflows/jira-agent.yaml` pra
desbloquear `git branch/commit/push` (fix do `permission_denials_count: 3`
observado no run 27479964934).

O fluxo do workflow precisava, em teoria, apenas de `git config / checkout /
add / commit / push` e `gh pr create / pr list`. Mas o allowlist autorizava
qualquer subcomando de `gh` e `git`. Combinado com SEC-006 (entrada
não-confiável da issue), isso amplificava o que um prompt malicioso podia
tentar (`gh release create`, `gh workflow run`, `gh api` arbitrário).

## Tentativa de fix granular e por que falhou

A próxima rodada de run (27480214579) mostrou que o gate de permissões da
`claude-code-action` é palavra-por-palavra: compostos como `command -v uv`,
`bash -lc '...'`, qualquer pipe ou `&&` exigem aprovação interativa que
não existe em CI. Mesmo `make test` (que invoca `uv` que invoca pytest)
foi negado. Enumerar tools que cobrem o que o agente pode tentar é
inviável — o conjunto depende do que a issue pede.

## Fix aceito

Remover `--allowed-tools` e usar `--dangerously-skip-permissions`. A
defesa real não está no gate do Claude — está em:

- **Runner efêmero GitHub-hosted** — destruído ao fim do job.
- **`permissions:` do job** — write apenas pra `contents`, `pull-requests`
  e `id-token`. Nada de `secrets: write`, `actions: write` (além do
  implícito do `GITHUB_TOKEN`).
- **`CLAUDE_CODE_OAUTH_TOKEN`** escopado a esta conta/repo.
- **Output é PR, não merge** — diff humano antes de tocar `main`.
- **Jira ACL no trigger** (SEC-006) — adversário externo já filtrado.

Tool gating dentro do Claude em cima desse perímetro era friction sem
valor incremental. Documentado em comentário no workflow apontando pra
esta issue.

## Trabalho relacionado

SEC-008 (artefato de log) — adicionado no mesmo PR pra dar visibilidade
post-mortem do que o agente fez quando algo der errado.

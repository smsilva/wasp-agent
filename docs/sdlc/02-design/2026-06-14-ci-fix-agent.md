# Jira Coding Agent v3 — ci-fix-agent (auto-fix de CI)

**Status:** Draft  
**Data:** 2026-06-14  
**Spec base (v2):** `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md`

---

## 1. Contexto

O `jira-agent.yaml` abre PRs no branch `claude/<ISSUE_KEY>`. Quando o CI
falha nesses PRs, a correção é manual. Este spec define dois novos workflows
que fecham esse ciclo: um notificador que avisa no PR quando o CI falha, e um
agente que tenta corrigir o código quando solicitado.

---

## 2. Arquivos novos

| Arquivo | Trigger | Responsabilidade |
|---|---|---|
| `.github/workflows/ci-fix-notifier.yaml` | `workflow_run` em `pull-request` (failure) | Detecta falha de CI em branch `claude/*`, posta convite `/fix` no PR |
| `.github/workflows/ci-fix-agent.yaml` | `issue_comment` | Detecta `/fix` no PR, conta tentativas, aciona `claude-code-action`, relata resultado |

---

## 3. Fluxo

```
pull-request.yaml falha em claude/PLTF-11
        ↓
ci-fix-notifier.yaml detecta via workflow_run
  - Busca PR pelo head_sha (gh pr list --head <sha>)
  - Se não há PR aberto: silencia
  - Se há PR: posta comentário com instrução /fix + link do run que falhou
        ↓
Usuário posta /fix (ou /fix --max-attempts 5)
        ↓
ci-fix-agent.yaml:
  1. Valida branch claude/* e permissão write+ do autor
  2. Extrai --max-attempts N do comentário (default: 3)
  3. Conta comentários <!-- ci-fix-attempt --> no PR
  4. Se contagem >= max_attempts → posta aviso, para (sem acionar agente)
  5. Invoca claude-code-action com prompt de correção
  6. Posta comentário <!-- ci-fix-attempt --> com link do run
  7. Se esgotou tentativas → jira-transition "In Progress" + jira-comment com resumo
```

---

## 4. ci-fix-notifier.yaml

```yaml
on:
  workflow_run:
    workflows: ["pull-request"]
    types: [completed]
```

- Roda apenas se `github.event.workflow_run.conclusion == 'failure'`
- Branch filtrada por `startsWith(github.event.workflow_run.head_branch, 'claude/')`
- Busca PR via `gh pr list --head <head_sha> --json number,url --jq '.[0]'`
- Se `number` vazio: encerra silenciosamente
- Posta comentário fixo:
  ```
  CI falhou ([ver run](<url_do_run>)). Responda `/fix` para tentar corrigir automaticamente.
  ```

---

## 5. ci-fix-agent.yaml

### 5.1 Trigger e filtros

```yaml
on:
  issue_comment:
    types: [created]
```

Condições no job (`if:`):
- `github.event.issue.pull_request` existe (é um PR, não uma issue)
- Corpo do comentário contém `/fix`
- Branch do PR começa com `claude/`
- Autor tem permissão `write` ou superior (via `gh api repos/:owner/:repo/collaborators/:user/permission`)

### 5.2 Loop-guard via contagem de comentários

Cada tentativa posta um comentário com marcador `<!-- ci-fix-attempt -->`. O
workflow conta esses comentários via `gh api` antes de acionar o agente. Se
`contagem >= max_attempts`, posta aviso e encerra sem invocar o agente.

`max_attempts` é extraído de `--max-attempts N` no corpo do comentário (regex
`--max-attempts\s+([0-9]+)`). Default: `3`.

### 5.3 Prompt do agente

```
CI falhou no PR <branch> (tentativa N de MAX).
Logs de falha: <URL do run>

Leia os logs, identifique a causa, corrija o código.
Faça commit e push na branch existente — não crie branch nova.
Não altere código não relacionado à falha.
```

O link do run que falhou é obtido buscando o último run do `pull-request`
workflow para o head SHA do PR via `gh run list`.

### 5.4 Pós-execução

- Posta comentário `<!-- ci-fix-attempt -->` com número da tentativa e link do run do `ci-fix-agent`
- O `pull-request.yaml` dispara automaticamente no novo push — o `ci-fix-agent` não monitora o resultado
- Falhas subsequentes requerem novo `/fix` manual (o `ci-fix-notifier` não repostar convite)

### 5.5 Esgotamento de tentativas

Quando `contagem >= max_attempts` (no início, antes de acionar o agente):

1. Posta comentário no PR com resumo das tentativas e links dos runs
2. Extrai `ISSUE_KEY` da branch: `claude/PLTF-11` → `PLTF-11`
3. `scripts/jira-transition <ISSUE_KEY> "In Progress"`
4. `scripts/jira-comment <ISSUE_KEY>` com número de tentativas e links dos runs

---

## 6. Secrets e permissões necessários

| Recurso | Origem |
|---|---|
| `GITHUB_TOKEN` | Automático (workflow); precisa de `pull-requests: write` para postar comentários |
| `CLAUDE_CODE_OAUTH_TOKEN` | Secret existente no repo |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` | Secrets existentes no repo |

Nenhum secret novo.

---

## 7. Critérios de sucesso

- CI falha em `claude/*` → comentário de convite aparece no PR automaticamente
- `/fix` posta → agente tenta corrigir e comenta resultado
- `/fix --max-attempts 5` → usa 5 como limite
- Após N tentativas esgotadas → issue Jira volta para "In Progress" com comentário de resumo
- PR permanece aberto independente do resultado
- Usuário sem permissão `write` posta `/fix` → sem efeito (silencioso)

---

## 8. Fora do escopo

- `workflow_dispatch` dry-run
- Extração de `scripts/jira-*` + `scripts/ensure-pr` para CLI Python
- Notificador republicar convite em falhas subsequentes (evita loop automático)
- Merge automático quando CI passa após correção

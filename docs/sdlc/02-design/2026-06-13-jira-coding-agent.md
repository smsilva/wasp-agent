# Jira Coding Agent — AI coding agent disparado por Jira via GitHub Actions

**Status:** Draft
**Data:** 2026-06-13
**Autor:** Silvio (brainstorming com Claude)

---

## 1. Contexto e hipótese

Queremos um agente de coding que reage a tickets do Jira: ao atribuir/transicionar
uma issue, um workflow do GitHub Actions implementa a tarefa, abre um PR e devolve o
status ao Jira. O agente — não o token de trigger — é responsável por todas as
operações de Git e Jira.

Antes de construir o fluxo completo, validamos a **hipótese de conectividade** com um
walking skeleton: provar o round-trip **Jira → GitHub → Jira** end-to-end, com cada
etapa interna no mínimo possível. O maior risco da hipótese não é a implementação do
código — é a **autenticação nos dois sentidos** e o roteamento do evento.

### O que NÃO é (nesta primeira versão)
- Não implementa código nenhum ainda (sem `claude -p`, sem branch, sem PR).
- Não trata ambiguidade de ticket nem falha de CI.
- Não extrai lógica para Python testado.

Essas peças entram em fases incrementais (§5).

---

## 2. Arquitetura alvo (visão completa)

```
Jira (transição "Ready for Agent" / atribuição ao agente)
   │  Jira Automation → POST repository_dispatch (trigger token de baixo privilégio)
   ▼
[A] jira-agent.yaml  (repository_dispatch)        ← pipeline de implementação (nosso)
   │  fetch Jira → branch → claude -p → push → PR → comenta/transiciona Jira
   ▼
PR aberto  ──CI roda──►  ci.yaml
                            │ falhou (conclusion=failure, head_branch agent/**)
                            ▼
                    [B] pr-agent.yaml  (workflow_run + issue_comment @claude)
                            └ claude-code-action oficial: analisa logs → comenta → auto-fix (com cap)
```

- **[A]** é orquestração customizada com `claude -p` headless. Lê o `CLAUDE.md` do repo
  nativamente.
- **[B]** é a action oficial `anthropics/claude-code-action`, com detecção automática de
  modo (`workflow_run` = corrige CI; `@claude` = interativo).
- O **bridge** Jira→GitHub é config no Jira (Automation rule), não código no repo.

Esta visão é o destino. A construção é faseada (§4 e §5).

---

## 3. Decisões de design (log)

| # | Decisão | Escolha | Racional |
|---|---|---|---|
| 1 | Onde vive / o que opera | Dentro do `wasp-agent`, agente edita o próprio repo | Feature do projeto |
| 2 | Motor de coding | Claude Code CLI **headless** (`claude -p`) | Lê `CLAUDE.md` nativo, tool loop maduro, menos cola |
| 3 | Identidade no GitHub | **GitHub App** dedicado, token efêmero | Atribuição limpa ao bot, permissão mínima, e PRs dele disparam o CI |
| 4 | Trigger Jira→GitHub | **`repository_dispatch`** (`event_type: jira-trigger-event`) | Payload `client_payload` carrega a issue key; trigger token só com `actions`/`contents:write` |
| 5 | Ticket ambíguo | Comenta perguntas + transiciona "Needs Info", **sem PR** | Falha segura (fase ≥ v3) |
| 6 | Falha de CI | PR agent (action oficial) analisa + comenta + **auto-fix** no branch | Loop autônomo até passar, com cap (fase ≥ v3) |
| 7 | Dry-run | Input booleano via `workflow_dispatch` de companhia | Iterar sem efeitos colaterais (fase ≥ v3) |

---

## 4. Versão 1 — walking skeleton (prova do round-trip)

Escopo mínimo: disparar o workflow e devolver um comentário ao Jira.

```
Jira: atribui/transiciona a issue
   └─ Automation → repository_dispatch (event_type: jira-trigger-event, client_payload.issue_key)
GitHub: jira-agent.yaml dispara (skeleton com todos os steps; só comentar é real)
   1. lê issue_key de github.event.client_payload.issue_key   [real]
   2. fetch / branch / claude / push / PR                      [stubs: só logam]
   3. comenta na issue do Jira: "Agent picked this up. Run: <run_url>"  [real]
```

Valida: autenticação Jira→GitHub (trigger token), roteamento do `repository_dispatch`,
e autenticação GitHub→Jira (API token para comentar).

### 4.1 Trigger — Jira Automation

Regra de Automation no Jira faz **Send web request**:

- **URL:** `https://api.github.com/repos/{owner}/wasp-agent/dispatches`
  (precisa do prefixo `api.github.com/repos/` — sem ele o POST retorna 404)
- **Method:** `POST`
- **Headers:**
  - `Authorization: Bearer <TRIGGER_TOKEN>`
  - `Accept: application/vnd.github+json`
- **Content-Type:** `application/json`
- **Body (custom data):**
  ```json
  {
    "event_type": "jira-trigger-event",
    "client_payload": { "issue_key": "{{issue.key}}" }
  }
  ```

`summary` não é enviado — fases posteriores fazem o fetch completo no Jira.

O **trigger token** é um PAT fine-grained de baixo privilégio (escopo `actions`/`contents:write`
no repo), guardado **no Jira**, nunca no repositório.

### 4.2 Workflow — `jira-agent.yaml`

```yaml
on:
  repository_dispatch:
    types: [jira-trigger-event]
```

Características do `repository_dispatch` a ter em mente:
- Só dispara com o arquivo de workflow no **branch default**.
- **Não** aparece na aba Actions como disparável manualmente — por isso a v1 já inclui um
  `workflow_dispatch` de companhia com input `jira_issue`, permitindo o primeiro teste de
  execução manual (pela aba Actions) sem depender do Jira. A issue key é normalizada de
  qualquer uma das fontes: `${{ github.event.client_payload.issue_key || inputs.jira_issue }}`.

**Skeleton completo de steps.** O workflow já tem **um step por etapa do pipeline alvo**,
mostrando a forma inteira end-to-end. Na v1, só o comentário no Jira é real; cada etapa
futura é um step próprio que **apenas loga** o que seria executado ali (placeholder de uma
linha — cabe na regra de "≤3 linhas inline"):

| Step | v1 |
|---|---|
| Ler `client_payload.issue_key` | **Real** |
| Fetch da issue no Jira | Stub — `echo "would fetch issue details for $ISSUE_KEY"` |
| Criar branch `agent/<KEY>-<slug>` | Stub — `echo "would create branch ..."` |
| Implementar com `claude -p` | Stub — `echo "would run claude -p to implement"` |
| Commit + push | Stub — `echo "would commit and push"` |
| Abrir PR | Stub — `echo "would open PR for <KEY>"` |
| Comentar + transicionar Jira | **Real** (comentário com o run URL via `scripts/jira-comment`) |

À medida que v2/v3 avançam, cada stub é substituído pela implementação real, sem mudar a
estrutura do workflow.

**Segurança do input:** `github.event.client_payload.*` é não-confiável. A issue key é
vinculada a uma env var (`ISSUE_KEY_RAW`) e validada por regex (`^[A-Z]+-[0-9]+$`) antes de
uso — nunca interpolada direto num `run:` (evita injeção de comando). `github.server_url`/
`repository`/`run_id` vêm do contexto do GitHub e são confiáveis.

### 4.3 Convenção de scripts (inegociável)

**Evitar scripts inline no YAML.** Qualquer passo com mais de 3 linhas de código vira um
**bash script em `scripts/`**, chamado pela action. Segue as regras globais de bash do
projeto (sem extensão no executável, long-form CLI options, 2-space indent, `set -e` para
sequências) e a convenção do `Makefile` ("quando um target precisa de mais de um comando,
extrai para `scripts/<name>`").

Script da v1: `scripts/jira-comment` — recebe issue key + texto, faz `POST` no endpoint
`/rest/api/3/issue/{key}/comment` do Jira (basic auth com `JIRA_EMAIL:JIRA_API_TOKEN`).

### 4.4 Secrets (v1)

Só o necessário para comentar de volta — **sem GitHub App ainda** (não há push/PR nesta
fase):

| Secret | Uso |
|---|---|
| `JIRA_BASE_URL` | Base da REST API do Jira |
| `JIRA_EMAIL` | Basic auth |
| `JIRA_API_TOKEN` | Basic auth |

---

## 5. Roadmap incremental

Cada versão adiciona uma fatia, mantendo o end-to-end sempre verde.

### v2 — implementação real (Status: Deferred)
- `actions/create-github-app-token` (GitHub App) → exige secrets `APP_ID`, `APP_PRIVATE_KEY`.
- `scripts/jira-fetch`: fetch dos detalhes da issue (`GET /rest/api/3/issue/{key}`), summary
  + description, ADF → markdown.
- `scripts/branch-name`: slug `agent/<KEY>-<slug-do-summary>`.
- `claude -p` implementa (lê `CLAUDE.md`) → exige `ANTHROPIC_API_KEY`.
- Commit + push + abre PR (título com a KEY, corpo com link pro Jira).
- `scripts/jira-transition`: comenta com a URL do PR + transiciona para "In Review".

### v3 — robustez (Status: Deferred)
- Gate de ambiguidade: primeira chamada `claude -p` classifica suficiência → JSON
  `{sufficient, questions[]}`; se insuficiente, comenta perguntas + "Needs Info", sem PR.
- `pr-agent.yaml`: action oficial em `workflow_run` (ci.yaml `failure`, `head_branch: agent/**`)
  e `issue_comment` (`@claude`). Auto-fix no branch com **loop-guard** (label `agent-fix:N`,
  para em 3 tentativas).
- `dry_run` como input do `workflow_dispatch` (já presente na v1) — roda o agente mas não
  faz push/PR/Jira.
- Extração da lógica para CLI Python testado (100% coverage, conforme `CLAUDE.md`).

(O `workflow_dispatch` de companhia com input `jira_issue` foi antecipado para a v1 — ver §4.2.)

---

## 6. Entregável: runbook reproduzível

Além do workflow e do script, a v1 entrega um **runbook** em
`docs/runbooks/jira-coding-agent-setup.md` documentando cada passo manual, para
replicar em outros repos e compartilhar como passo a passo. Mapa dos passos a documentar:

**Lado Jira:**
1. Criar API token (id.atlassian.com) → guardar para os secrets do GitHub.
2. Criar a Automation rule: trigger (atribuição/transição) → action "Send web request"
   com URL, headers e body do §4.1.
3. Onde colar o trigger token (Jira, não GitHub) e como referenciá-lo.

**Lado GitHub:**
4. Criar o trigger token: PAT fine-grained com `contents: write` no repo.
5. Adicionar os secrets `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` (Settings → Secrets).
6. Mergear `jira-agent.yaml` no branch default (requisito do `repository_dispatch`).

**Validação:**
7. Disparar atribuindo uma issue de teste; conferir o run na aba Actions e o comentário no Jira.
8. Troubleshooting comum (404 no dispatch = URL sem `api.github.com/repos/`; 401 = token/escopo).

Cada versão posterior (v2, v3) estende este mesmo runbook com seus passos novos
(criar GitHub App, adicionar `APP_ID`/`APP_PRIVATE_KEY`/`ANTHROPIC_API_KEY`, etc.).

---

## 7. Critérios de sucesso da v1

- Atribuir/transicionar uma issue no Jira dispara o `jira-agent.yaml` (run visível na aba Actions).
- O run termina verde e a issue do Jira recebe um comentário com o link do run.
- Nenhum secret de longa duração vive no repositório (trigger token fica no Jira).
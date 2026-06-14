# Jira Coding Agent v3 — SEC-008 fix (execution log artifact)

**Status:** Draft
**Data:** 2026-06-13
**Spec base (v2):** `docs/sdlc/02-design/2026-06-13-jira-coding-agent-v2.md`
**Security issue:** `docs/security/issues/SEC-008-jira-agent-execution-log-artifact.md`

---

## 1. Contexto

PR #7 adicionou ao `jira-agent.yaml` dois steps que coletam e publicam
`/home/runner/work/_temp/claude-execution-output.json` num artefato
`claude-execution-log-<ISSUE_KEY>.tar.gz` com `if: always()` e
`retention-days: 30`. O JSON contém prompt completo, cada `tool_use`/
`tool_result`, saída de shell rodada pelo agente e a resposta final do
modelo. SEC-008 catalogou o vetor: amplificação de leitura (ACL do Jira ≠
ACL do GitHub), exposição acidental de env vars e canal de exfiltração
assíncrona por prompt injection.

Severity Low porque o repo é privado e o artefato é read-only. Pré-condições
para mexer agora, declaradas no próprio SEC-008.md §"Fix planejado", já
estão satisfeitas: PR #7 desbloqueou PLTF-11 (run verde) e o primeiro
artefato útil foi consumido.

---

## 2. Decisão

Aplicar mitigações (1) + (4) do SEC-008.md numa única mudança no workflow:

| Step | Antes | Depois |
|---|---|---|
| `Collect Claude execution log` | `if: always()` | `if: failure()` |
| `Upload Claude execution log` | `if: always()`, `retention-days: 30` | `if: failure()`, `retention-days: 7` |

Nada mais muda. Mitigação (2) (sanitização por `jq`) descartada — "vira
jogo de gato e rato". Mitigação (3) (ACL granular) descartada — GitHub
não oferece esse controle por artefato.

**Consequência operacional aceita:** runs verdes deixam de produzir
log post-mortem, perdendo amostragem para evolução do agente. SEC-008.md
e este spec consideram a troca aceitável: sucesso não precisa de
post-mortem; falha precisa.

---

## 3. Arquivos tocados

- `.github/workflows/jira-agent.yaml` — dois `if: always()` viram
  `if: failure()`; `retention-days: 30` vira `7`.
- `docs/security/issues/SEC-008-jira-agent-execution-log-artifact.md`
  — `status: open` vira `status: resolved`; mover para `archived/`.
- `HANDOFF.md` — remover bullet "SEC-008" de **Known Broken** e
  remover "Resolver SEC-008" do bullet da v3 em **Backlog**.
- `docs/sdlc/CLAUDE.md` — adicionar este spec à tabela de 02-design.

Sem mudança em código Python, sem mudança em scripts bash, sem novos
secrets. `make test`/`make e2e` permanecem inalterados.

---

## 4. Validação

1. **Run verde:** disparar PLTF-11 (issue de teste) ou criar issue
   nova; conferir na aba Actions que nenhum artefato
   `claude-execution-log-*` foi publicado.
2. **Run com falha:** forçar falha (ex.: secret Jira inválido
   temporariamente, ou `workflow_dispatch` com `jira_issue: PLTF-9999`
   inexistente); conferir que o artefato aparece com
   `retention-days: 7`.

Os dois caminhos cobrem a mudança inteira. Não há código Python a
testar.

---

## 5. Critérios de sucesso

- Runs verdes do `jira-agent.yaml` não produzem artefato.
- Runs vermelhos do `jira-agent.yaml` produzem artefato com retenção
  de 7 dias.
- SEC-008 movido para `archived/` com `status: resolved`.
- `HANDOFF.md` reflete o fechamento (sai de Known Broken; sai do
  escopo do v3 no Backlog).

---

## 6. Fora do escopo

- `pr-agent.yaml` (auto-fix de CI no PR do agente).
- `workflow_dispatch` dry-run.
- Extração de `scripts/jira-*` + `scripts/ensure-pr` para CLI Python.
- Sanitização de campos no JSON do artefato.

Cada um vira spec próprio na sequência da v3 (4 specs, 4 planos, conforme
decidido no brainstorming).

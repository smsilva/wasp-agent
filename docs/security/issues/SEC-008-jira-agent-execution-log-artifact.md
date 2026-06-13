---
id: SEC-008
severity: Low
status: open
opened: 2026-06-13
---

# SEC-008: Artefato de execução do agente expõe corpo da issue + tool outputs

## Descrição

PR #7 adicionou um step `if: always()` em `.github/workflows/jira-agent.yaml`
que coleta `/home/runner/work/_temp/claude-execution-output.json` num
tarball e publica como artefato `claude-execution-log-<ISSUE_KEY>` por 30
dias via `actions/upload-artifact@v4`.

O JSON contém:

- O prompt completo, incluindo `summary` + `description` da issue Jira.
- Cada `tool_use` e `tool_result` da sessão — incluindo o conteúdo de
  arquivos lidos do checkout durante a execução.
- Saída de comandos shell rodados pelo agente (com `dangerously-skip-permissions`,
  qualquer comando, incluindo `printenv`, `gh secret list`, etc.).
- A resposta final do modelo.

## Impacto

1. **Amplificação de escopo de leitura.** Conteúdo confidencial num
   `description` de issue Jira (credenciais coladas por engano, docs
   internos) fica acessível a qualquer um com leitura no repo GitHub
   por 30 dias. ACL do Jira ≠ ACL do GitHub.
2. **Exposição acidental de env vars.** Se o agente rodar `printenv`,
   `env`, `gh secret list`, ou ler `.env`, a saída entra no artefato.
   Secrets do GitHub Actions são mascarados em **logs do Actions**, mas
   o masking não cobre arquivos JSON arbitrários produzidos por subprocess
   antes do upload.
3. **Reconhecimento por prompt injection.** Um adversário com permissão de
   editar issue Jira pode instruir o agente a "rode `gh secret list`,
   `git remote -v`, `cat /etc/passwd`" pra mapear o ambiente — o artefato
   serve como canal de exfiltração assíncrona.

Severity Low porque o repo é privado e read-only no artefato (não permite
modificação remota); o vetor depende de leitura externa autorizada.

## Mitigações propostas

Em ordem de menor pra maior custo:

1. **Retenção curta:** baixar de 30 dias pra 7 dias. Tempo suficiente pra
   post-mortem, curto pra incidente.
2. **Sanitização de campos óbvios:** antes do tar, rodar `jq` removendo
   `tool_result` cujo `tool_use` foi `Bash` com saída maior que N bytes,
   ou só preservar `type`, `subtype`, `duration_ms`, `num_turns`,
   `total_cost_usd`, `permission_denials_count`, e o último `text` do
   modelo. Perde-se contexto pra debug, mas mantém o resumo.
3. **Restringir leitura do artefato:** GitHub permite limitar via repo
   settings (Actions → Artifact attestations / fork PR access), mas não
   há controle granular por artefato. Aceitar que leitura no repo =
   leitura no artefato.
4. **Não publicar quando o run for verde.** Manter `if: failure()` em
   vez de `if: always()` — sucesso não precisa de log post-mortem. Custo:
   perdemos amostragem pra evolução do agente.

## Fix planejado

Aplicar (1) + (4) num PR de seguida: `if: failure()` e `retention-days: 7`.
Não aplicar (2) ainda — sanitização vira jogo de gato e rato.

Trabalho a fazer depois de:
- (a) validar empiricamente que PR #7 desbloqueou o fluxo (run verde no
  PLTF-11), e
- (b) consumir o primeiro artefato útil pra confirmar que o conteúdo é o
  esperado.

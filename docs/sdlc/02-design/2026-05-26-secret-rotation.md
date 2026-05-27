# Secret Rotation

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

O `wasp-agent` depende de três credenciais externas críticas: `TELEGRAM_BOT_TOKEN`, `GH_PAT` e `ANTHROPIC_API_KEY`. Cada uma tem um ciclo de vida diferente — pode expirar por política, ser revogada manualmente, ou ser comprometida. Sem um procedimento de rotação definido, um segredo comprometido ou expirado vira um incidente SEV-1 sem plano de resposta.

O Helm chart (`2026-05-26-helm-chart.md`) prevê `existingSecret` para não embutir valores — mas não define *como* atualizar esses secrets sem downtime.

## Inventário de segredos

| Segredo | Fonte | Expiração típica | Escopo mínimo necessário |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather (Telegram) | Não expira; revogável | N/A (token único do bot) |
| `GH_PAT` | GitHub Settings | 30/60/90 dias (fine-grained) ou nunca (classic) | `contents:write` no repo GitOps específico |
| `ANTHROPIC_API_KEY` | console.anthropic.com | Não expira; revogável | N/A (chave de API) |

## Procedimento de rotação por segredo

### `GH_PAT` (rotação mais frequente)

PATs fine-grained do GitHub têm expiração configurável. Procedimento:

1. Criar novo PAT com mesmo escopo **antes** de revogar o anterior.
2. Atualizar o Kubernetes Secret: `kubectl create secret generic wasp-agent-secrets --from-literal=GH_PAT=<novo> --dry-run=client -o yaml | kubectl apply -f -`
3. Reiniciar o pod para recarregar: `kubectl rollout restart deployment/wasp-agent`
4. Verificar com `make smoke-gitops` ou `wasp/startup.py` → `GitOpsCommitter.probe()`.
5. Revogar o PAT anterior no GitHub.

Sem downtime: o pod antigo usa o token válido até o rollout completar; o novo pod usa o novo token.

**Alerta proativo:** adicionar lembrete no calendário ou Alertmanager rule avisando 7 dias antes da expiração do PAT. `GH_PAT` expirando é o incidente mais previsível do sistema.

### `TELEGRAM_BOT_TOKEN`

Token não expira, mas pode ser necessário revogar (bot comprometido):

1. No BotFather: `/revoke` → novo token gerado imediatamente.
2. Atualizar Kubernetes Secret (mesmo procedimento do PAT).
3. Reiniciar pod.
4. Reconfigurar webhook: `POST https://api.telegram.org/bot<novo_token>/setWebhook?url=<url>`

**Atenção:** após revogação, o token antigo para de funcionar imediatamente. Janela de indisponibilidade = tempo do rollout (~30s).

### `ANTHROPIC_API_KEY`

1. Em console.anthropic.com: criar nova chave.
2. Atualizar Kubernetes Secret.
3. Reiniciar pod.
4. Desativar chave antiga no console.

## Rotação de emergência (segredo comprometido)

Se um segredo foi exposto (commit acidental, log, screenshot):

1. **Revogar imediatamente** — antes de qualquer outra ação. Tempo entre exposição e revogação = janela de abuso.
2. Auditar logs do período de exposição: acessos suspeitos? operações não autorizadas?
3. Criar novo segredo e seguir procedimento de rotação.
4. Criar entry em `docs/security/issues/` com timeline, escopo de exposição e ações tomadas.
5. Verificar com `gitleaks` / `trufflehog` se o segredo está em outros commits do histórico — se sim, reescrever histórico ou considerar o repo como comprometido.

## Automação de rotação

### External Secrets Operator (ESO)

Com ESO, o Kubernetes Secret é sincronizado automaticamente de um secrets manager externo (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault):

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: wasp-agent-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: wasp-agent-secrets
  data:
    - secretKey: GH_PAT
      remoteRef:
        key: wasp-agent/gh-pat
```

Com `refreshInterval: 1h`, o Secret é atualizado automaticamente quando o valor no secrets manager muda — zero intervenção manual, zero downtime se o pod recarregar o valor dinamicamente.

**Requer:** pod recarregando segredo em runtime (não só no startup) — ou `refreshInterval` + `kubectl rollout restart` via CronJob.

### Rotação automática de PAT

GitHub não suporta rotação automática de PATs nativamente. Alternativas:

- **GitHub App** em vez de PAT: tokens de curta duração (1h) gerados automaticamente. Mais seguro, mais complexo.
- **Script de rotação** via GitHub CLI + Kubernetes Secret update, executado por CronJob antes da expiração.

## Auditoria

Cada rotação de segredo deve gerar um registro em `docs/runbooks/secret-rotation-log.md` (ou equivalente):

```
| Data | Segredo | Motivo | Executado por | Verificado |
|------|---------|--------|---------------|------------|
| 2026-06-01 | GH_PAT | Expiração programada | Silvio | ✓ |
```

Auditoria de rotações é evidência de controle de segurança para fins de conformidade (EU AI Act / CRA).

## Conexão com outros specs

- **Helm chart (`2026-05-26-helm-chart.md`):** `existingSecret` é o mecanismo; este spec é o procedimento de atualização.
- **Incident Response (`2026-05-26-incident-response.md`):** rotação de emergência é um runbook de incidente — criar `docs/runbooks/incident-secret-compromised.md`.
- **SBOM / Supply Chain (`2026-05-26-supply-chain-security.md`):** COSIGN usa identidade OIDC (keyless) — sem chave privada para rotacionar. Modelo mais seguro.
- **EU AI Act (`2026-05-26-eu-ai-act.md`):** auditabilidade de rotações é parte de "gestão de risco" (Art. 9) para sistemas de alto risco.

## Armadilhas

- **Revogar antes de atualizar.** Sempre criar novo segredo antes de revogar o antigo — nunca o inverso. Janela de indisponibilidade desnecessária.
- **PAT com escopo excessivo.** `GH_PAT` com `repo:*` em vez de `contents:write` no repo específico. Escopo mínimo limita blast radius se comprometido.
- **Segredo em variável de ambiente no Dockerfile.** `ENV GH_PAT=...` no Dockerfile gravar o segredo na imagem — visível em `docker inspect`. Sempre via Secret do Kubernetes, nunca via `ENV`.
- **Sem alerta de expiração.** PAT expira silenciosamente; agente começa a falhar sem mensagem clara. Monitorar expiração é mais barato que responder ao incidente.

## Fora de escopo desta nota

- Rotação automática de certificados TLS (cert-manager cuida disso).
- Gestão de secrets para ambientes múltiplos (dev/staging/prod) — depende de decisão de multi-environment.
- GitHub App como substituto de PAT — alternativa mais robusta mas requer mudança em `wasp/gitops.py`.

## Próximo passo

Criar `docs/runbooks/secret-rotation-log.md` e documentar a data de criação e expiração do PAT atual. Ação imediata: verificar se o PAT atual é fine-grained ou classic — migrar para fine-grained com escopo mínimo se ainda for classic.

## Referências

- [GitHub fine-grained PATs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [External Secrets Operator](https://external-secrets.io/)
- [Kubernetes Secrets best practices](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)
- [gitleaks](https://github.com/gitleaks/gitleaks) — detectar segredos no histórico git
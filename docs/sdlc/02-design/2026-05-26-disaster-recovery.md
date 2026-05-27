# Disaster Recovery

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

O `wasp-agent` persiste estado em SQLite (`wasp/auth.db`): usuários autorizados, convites, admin bootstrap. Se esse banco for perdido (pod deletado sem PVC, PVC deletado, corrupção), o sistema perde toda a informação de autorização — nenhum usuário consegue usar o agente até que o admin seja rebootstrapado manualmente.

Disaster recovery responde: **qual é o estado crítico? onde fica? como é preservado? como é restaurado?**

## Definições

**RTO (Recovery Time Objective):** tempo máximo aceitável de indisponibilidade após um desastre. Quanto tempo o sistema pode ficar fora?

**RPO (Recovery Point Objective):** perda máxima aceitável de dados. Até quando o backup pode ter sido feito?

Para `wasp-agent` (projeto pessoal, poucos usuários):

- **RTO sugerido:** 1 hora (tempo de rebootstrap manual + comunicação).
- **RPO sugerido:** 24 horas (backup diário é suficiente — perder um dia de novos convites é tolerável).

Ajustar conforme criticidade real quando houver mais usuários.

## Inventário de estado

| Estado | Onde fica | Criticidade | Reproduzível sem backup? |
|---|---|---|---|
| `wasp/auth.db` | Pod filesystem / PVC | **Alta** | Não — lista de usuários é insubstituível |
| Repos GitOps provisionados | Gitea / GitHub | Média | Sim — Gitea tem seu próprio backup; GitHub é externo |
| Logs | stdout / log aggregator | Baixa | Sim — logs históricos para auditoria, não para recovery |
| Métricas Prometheus | Prometheus (se persistido) | Baixa | Sim — métricas históricas perdem-se, não afetam operação |
| Segredos (`GH_PAT`, etc.) | Kubernetes Secret / .env | Alta | Depende — segredos podem ser recriados mas geram downtime |
| System prompt | `wasp/prompts/system.md` | Média | Sim — está no git |
| Configuração | `values.yaml` + ConfigMap | Média | Sim — está no git |

**Conclusão:** o único estado verdadeiramente irrecuperável sem backup é `wasp/auth.db`.

## Estratégia de backup do SQLite

### Opção A — Backup periódico via CronJob Kubernetes

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: wasp-agent-db-backup
spec:
  schedule: "0 3 * * *"   # diário às 3h
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: alpine
              command:
                - sh
                - -c
                - |
                  sqlite3 /data/auth.db ".backup /backup/auth-$(date +%Y%m%d).db"
                  find /backup -name "*.db" -mtime +7 -delete
              volumeMounts:
                - name: db-volume
                  mountPath: /data
                - name: backup-volume
                  mountPath: /backup
```

**Destino do backup:** PVC separado, ou object storage (S3/GCS) via `rclone`.

### Opção B — Replicação para object storage

```bash
# script de backup
sqlite3 /data/auth.db ".backup /tmp/auth-backup.db"
rclone copy /tmp/auth-backup.db s3:bucket/wasp-agent/backups/
```

Mais resiliente que PVC — sobrevive a falha de node/cluster.

### Opção C — Export periódico para formato texto

```bash
sqlite3 /data/auth.db .dump > /backup/auth-$(date +%Y%m%d).sql
```

Mais portável que arquivo binário SQLite — pode ser reimportado em qualquer versão do SQLite.

**Recomendação:** Opção C (dump SQL) + upload para S3/GCS para projeto que já usa cloud. Para projeto totalmente local: Opção A com PVC separado.

## Procedimento de restore

### Cenário 1: Pod perdido, PVC intacto

PVC sobrevive a deleção de pod por default. Basta recriar o pod/deployment:
```bash
kubectl rollout restart deployment/wasp-agent
```
Nenhuma ação adicional necessária.

### Cenário 2: PVC perdido, backup disponível

```bash
# 1. Recriar PVC
kubectl apply -f pvc.yaml

# 2. Restaurar backup no PVC via pod temporário
kubectl run restore --image=alpine --rm -it \
  --overrides='{"spec":{"volumes":[{"name":"db","persistentVolumeClaim":{"claimName":"wasp-agent-db"}}],"containers":[{"name":"restore","image":"alpine","command":["sh"],"volumeMounts":[{"name":"db","mountPath":"/data"}]}]}}'

# 3. Dentro do pod: copiar backup e restaurar
cp /backup/auth-20260526.db /data/auth.db

# 4. Reiniciar agente
kubectl rollout restart deployment/wasp-agent

# 5. Verificar auth funcionando
make smoke-auth  # ou teste manual via Telegram
```

### Cenário 3: Banco corrompido

SQLite tem mecanismo de integridade:
```bash
sqlite3 /data/auth.db "PRAGMA integrity_check;"
```

Se corrompido: `sqlite3 /data/auth.db ".recover" | sqlite3 /data/auth-recovered.db` — tenta recuperar dados legíveis. Se falhar completamente: restore do backup.

### Cenário 4: Sem backup, banco perdido (pior caso)

1. Rebootstrap do admin: `make bootstrap-admin CHAT_ID=<admin_chat_id>` (ou equivalente).
2. Admin recria convites para usuários existentes.
3. Comunicar usuários afetados.

Documentar IDs de usuários autorizados fora do banco (planilha, nota segura) como fallback para este cenário.

## Verificação periódica de backup

Um backup não testado é um backup não confiável. Procedimento mensal:

1. Baixar backup mais recente.
2. `sqlite3 auth-backup.db "PRAGMA integrity_check;"` — deve retornar `ok`.
3. `sqlite3 auth-backup.db "SELECT COUNT(*) FROM auth_users;"` — deve retornar número esperado.
4. Registrar resultado em `docs/runbooks/disaster-recovery-log.md`.

## Conexão com outros specs

- **Helm chart (`2026-05-26-helm-chart.md`):** `persistence.enabled: true` com PVC é pré-requisito para Opções A e B. Sem PVC, o banco é efêmero por design.
- **Incident Response (`2026-05-26-incident-response.md`):** perda de banco é SEV-1 — este spec é o runbook de restore.
- **Secret Rotation (`2026-05-26-secret-rotation.md`):** segredos Kubernetes são estado separado do banco — têm seu próprio procedimento de recovery.
- **Privacy / Data Retention (`2026-05-26-privacy-data-retention.md`):** backups contêm dados pessoais (`chat_id`, usernames) — aplicar mesma política de retenção e acesso.

## Armadilhas

- **PVC no mesmo node que o pod.** `storageClass` local-path vincula PVC ao node — se o node morrer, PVC some junto. Usar `storageClass` com replicação (Longhorn, Rook-Ceph) ou object storage.
- **Backup sem teste de restore.** Testar o restore uma vez antes de precisar dele.
- **SQLite em modo WAL sem checkpoint.** WAL mode cria arquivos `-wal` e `-shm` — backup deve incluir os três arquivos ou usar `sqlite3 .backup` (que faz checkpoint automático).
- **Backup no mesmo volume que o banco.** Um evento que corrompe o volume primário corromperia o backup também. Sempre destino separado.

## Fora de escopo desta nota

- HA (High Availability) com réplica ativa do banco — requer migração para Postgres.
- Backup de cluster Kubernetes inteiro (Velero) — escopo de infra, não do agente.
- Replicação geográfica — para projeto pessoal é overkill.

## Próximo passo

Promover a Draft junto com o Helm chart — PVC é pré-requisito para qualquer estratégia de backup. Ação imediata de custo zero: documentar os `chat_id`s dos usuários autorizados atuais em local seguro fora do banco (fallback para Cenário 4).

## Referências

- [SQLite Backup API](https://www.sqlite.org/backup.html)
- [SQLite `.backup` command](https://www.sqlite.org/cli.html#special_commands_to_sqlite3_dot_commands_)
- [Velero — cluster backup](https://velero.io/)
- [rclone — sync para object storage](https://rclone.io/)

---
id: SEC-002
severity: Low
status: open
opened: 2026-05-13
---

# SEC-002: `agent.db` tem permissão world-readable

## Descrição

O banco SQLite criado em runtime (`agent.db`) tem permissão `644`. Qualquer usuário local pode ler o arquivo, que contém histórico completo de conversas do Telegram.

## Evidência

```
-rw-r--r-- 1 silvios domain users 364544 agent.db
```

## Impacto

Em servidor compartilhado, outros usuários com acesso ao filesystem leem o histórico de conversas (PII dos usuários do bot).

Sem impacto em deployment via container com usuário dedicado.

## Fix

Restringir permissões via `umask` antes de iniciar o processo, ou no entrypoint:

```bash
umask 0077        # arquivos criados com 600
# ou após criação:
chmod 600 agent.db
```
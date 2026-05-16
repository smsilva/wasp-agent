# Platform watcher — restart resilience

## Status

Deferred — implementar após o MVP do watcher do Ciclo 3.

## Contexto

O Ciclo 3 introduz um watcher in-process (`asyncio.create_task`) que observa o status de cada `Platform` CRD provisionada e notifica o usuário no Telegram quando `Ready: True`.

No MVP, watches são puramente in-memory: se o processo do agente cair ou for reiniciado antes de a Platform ficar Ready, a notificação é perdida. O usuário precisaria pedir status manualmente.

## Problema

Após restart do agente:

- Tasks `asyncio` em execução desaparecem
- Platforms ainda reconciliando ficam órfãs do ponto de vista de notificação
- O usuário não recebe o "Ready" prometido implicitamente quando aceitou a confirmação de provisionamento

## Proposta

Persistir o estado dos watches ativos em SQLite e recarregá-los no startup.

### Schema

Tabela `platform_watches`:

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `name` | TEXT PRIMARY KEY | Nome da Platform (cluster-scoped) |
| `session_id` | TEXT NOT NULL | `tg:{entity_id}:{chat_id}` — destino da notificação |
| `status` | TEXT NOT NULL | `pending` \| `ready` \| `failed` |
| `created_at` | TIMESTAMP | Momento da criação do watch |
| `notified_at` | TIMESTAMP NULL | Momento em que a notificação foi enviada |

### Comportamento no startup

1. `SELECT * FROM platform_watches WHERE status = 'pending'`
2. Para cada linha, spawn um novo `asyncio.create_task` que observa o `Platform` correspondente
3. Se a Platform já não existe no cluster (foi deletada manualmente), marcar `status = 'failed'` e logar
4. Se já está `Ready: True`, enviar notificação imediatamente

### Comportamento durante operação

- Ao registrar um novo watch: INSERT com `status = 'pending'`
- Ao detectar `Ready: True`: enviar notificação, depois UPDATE `status = 'ready'`, `notified_at = now()`
- Em erros irrecuperáveis (timeout, CRD removida): UPDATE `status = 'failed'`

### Garantias

- **At-least-once**: se o agente cair entre o envio da notificação e o UPDATE, o usuário pode receber a notificação duplicada no próximo startup. Aceitável.
- **Não at-most-once**: o agente não tenta deduplicar via flag externo.

## Fora de escopo

- Retentativas de notificação se a Telegram API falhar (delegar à próxima reconciliação do watch)
- Limpeza retroativa de watches antigos (`status = 'ready'` há > N dias) — fazer com job separado se a tabela crescer
- Migrações de schema — usar `CREATE TABLE IF NOT EXISTS` no startup

## Riscos

- Race condition entre INSERT e o início do task `asyncio` — mitigar fazendo INSERT antes do `create_task`
- Crescimento ilimitado da tabela — aceitar no MVP; revisitar quando passar de ~10k linhas

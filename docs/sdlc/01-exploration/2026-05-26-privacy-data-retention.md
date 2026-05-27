# Privacy e Retenção de Dados

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

O `wasp-agent` processa mensagens de usuários via Telegram, persiste identidades em SQLite e gera logs com `chat_id` e conteúdo de operações. Esses são dados pessoais sob o GDPR (Regulamento Geral de Proteção de Dados, UE 2016/679). Hoje o projeto é pessoal — mas as decisões de arquitetura tomadas agora determinam o custo de conformidade quando houver usuários reais.

Este spec não visa conformidade formal completa — visa **decisões de design que não criem débito de privacidade**.

## O que é coletado

### Dados de identidade (SQLite `auth.db`)

| Dado | Tabela/campo | Finalidade | Sensibilidade |
|---|---|---|---|
| `chat_id` (Telegram) | `auth_users.channel_id` | Identificar usuário autorizado | Alta — identificador único de pessoa |
| `channel` | `auth_users.channel` | Routing de notificações | Baixa |
| `username` / `first_name` | Não armazenado hoje | — | — |
| `invite_code` | `invites.code` (hash?) | Controle de acesso | Média |

### Dados de sessão (memória / logs)

| Dado | Onde | Finalidade | Sensibilidade |
|---|---|---|---|
| `chat_id` | Logs estruturados | Rastreabilidade de erros | Alta |
| Conteúdo de mensagens | Logs (se logado) | Debug | Alta — pode conter informações do usuário |
| Tool call arguments | Logs | Auditoria de operações | Média — pode conter nomes de plataformas |
| Tokens/custo por sessão | Métricas (sem identificação) | Observabilidade | Baixa |

### Dados enviados a terceiros

| Terceiro | Dado enviado | Base legal necessária |
|---|---|---|
| **Anthropic API** | Conteúdo completo das mensagens | Necessário para o serviço |
| **GitHub API** | Nome de plataforma, commits | Necessário para o serviço |
| **Telegram API** | Respostas do agente | Necessário para o serviço |

**Ponto crítico:** mensagens do usuário são enviadas à Anthropic para processamento. A política de dados da Anthropic aplica. Usuários devem ser informados disso.

## Princípios de privacy by design

### 1. Minimização de dados
Coletar apenas o necessário. `chat_id` é necessário; `username`, `first_name`, `phone_number` do Telegram geralmente não são.

**Ação:** verificar se `wasp/auth.py` armazena campos além de `channel_id` e `channel`. Se armazena, avaliar necessidade.

### 2. Limitação de finalidade
Dados coletados para autenticação não devem ser usados para analytics de comportamento.

**Ação:** `chat_id` em logs deve ser para rastreabilidade de erros, não para perfilamento de uso.

### 3. Retenção limitada
Dados não devem ser mantidos além do necessário.

### 4. Transparência
Usuários devem saber que dados são coletados e o que acontece com suas mensagens.

## Política de retenção

| Dado | Retenção proposta | Mecanismo de expiração |
|---|---|---|
| `auth_users` (usuários ativos) | Enquanto usuário ativo | Revogação manual via admin |
| `auth_users` (usuários revogados) | 90 dias após revogação | Script de limpeza periódico |
| `invites` (usados) | 30 dias após uso | Script de limpeza periódico |
| Logs de aplicação | 30 dias | Log rotation (`logrotate` ou política do aggregator) |
| Backups do banco | 7 dias de retenção (FIFO) | Script de backup com cleanup |
| Traces (OpenTelemetry) | 7 dias | Política do backend (Jaeger/Tempo TTL) |
| Métricas Prometheus | 15 dias | `--storage.tsdb.retention.time=15d` |

## Direito ao apagamento (GDPR Art. 17)

Se um usuário solicitar apagamento de seus dados:

```sql
-- Remover usuário do allowlist
DELETE FROM auth_users WHERE channel = ? AND channel_id = ?;

-- Remover convites usados pelo usuário (se rastreado)
DELETE FROM invites WHERE redeemed_by = ?;
```

Logs já emitidos não podem ser "desemitidos" — mas podem ser retidos por período limitado (ver tabela acima) e não indexados por PII.

**Ação:** criar comando admin `make forget-user CHANNEL=tg CHANNEL_ID=123` que executa o apagamento e confirma.

## Anonimização de logs

`chat_id` em logs é PII. Estratégias:

**Pseudonimização (recomendado):** substituir `chat_id` por hash `sha256(chat_id + salt)[:8]` nos logs de produção. Rastreabilidade interna mantida; não identificável externamente sem o salt.

```python
def pseudonymize(chat_id: str, salt: str) -> str:
    return hashlib.sha256(f"{chat_id}{salt}".encode()).hexdigest()[:8]

logger.info("webhook_received", extra={"user_ref": pseudonymize(chat_id, LOG_SALT)})
```

**Redação total:** não logar `chat_id` — perde rastreabilidade de debug.

Para projeto pessoal com usuários conhecidos: pseudonimização é o ponto de equilíbrio.

## Transparência para usuários

Mensagem de onboarding (`/start` ou primeira interação) deve incluir:

> Este agente processa suas mensagens usando a API da Anthropic (Claude). Suas mensagens são enviadas à Anthropic para processamento. Nenhum conteúdo de mensagens é armazenado permanentemente por este agente — apenas seu identificador de usuário para controle de acesso.

Conecta com EU AI Act Art. 50.1 (`2026-05-26-eu-ai-act.md`).

## Transferência internacional de dados

Anthropic é empresa americana — mensagens enviadas à API são transferidas para os EUA. Sob GDPR, transferências internacionais requerem base legal (Standard Contractual Clauses, adequacy decision, etc.). Anthropic tem DPA (Data Processing Agreement) disponível para assinatura.

Para projeto pessoal: risco baixo. Para produto comercial com usuários UE: assinar DPA da Anthropic antes de onboardar usuários.

## Conexão com outros specs

- **Disaster Recovery (`2026-05-26-disaster-recovery.md`):** backups contêm dados pessoais — mesma política de acesso e retenção aplica aos backups.
- **OpenTelemetry (`2026-05-26-opentelemetry-tracing.md`):** atributos de span não devem conter conteúdo de mensagens — apenas `chat_id` pseudonimizado e metadados.
- **EU AI Act (`2026-05-26-eu-ai-act.md`):** Art. 10 (data governance) para sistemas de alto risco; Art. 50 (transparência) para todos os chatbots.
- **Auth (`wasp/auth.py`):** é o sistema de registro de dados pessoais — deve ter mecanismo de apagamento.
- **Incident Response (`2026-05-26-incident-response.md`):** vazamento de dados é SEV-1 com obrigação de notificação em 72h sob GDPR.

## Armadilhas

- **Logar conteúdo de mensagens em DEBUG.** Prático para desenvolvimento, desastroso em produção. Garantir que `LOG_LEVEL=DEBUG` não vaza para produção.
- **`chat_id` em labels de métricas Prometheus.** Labels com alta cardinalidade (um valor por usuário) explodem o uso de memória do Prometheus. Nunca usar `chat_id` como label — usar como atributo de span em traces.
- **Backup sem controle de acesso.** Arquivo de backup com `auth.db` em S3 público = exposição de todos os usuários. Bucket privado + IAM mínimo.
- **Confundir retenção técnica com retenção legal.** Manter logs por 7 dias é decisão técnica; GDPR pode exigir manutenção de logs de auditoria por mais tempo para fins de compliance. Verificar se aplica.

## Fora de escopo desta nota

- DPIA (Data Protection Impact Assessment) formal — exigido para processamento de alto risco sob GDPR.
- Registro de atividades de processamento (Art. 30 GDPR) — para organizações, não projetos pessoais.
- Política de cookies — não aplicável (sem interface web).

## Próximo passo

Promover a Draft quando houver usuários além do próprio desenvolvedor. Ação imediata: auditar `wasp/auth.py` para confirmar que apenas `channel` e `channel_id` são armazenados (sem `username`, `first_name` do Telegram desnecessários) e adicionar mensagem de transparência no onboarding.

## Referências

- [GDPR — texto oficial](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
- [Anthropic Privacy Policy](https://www.anthropic.com/privacy)
- [Anthropic DPA](https://www.anthropic.com/legal/data-processing-addendum)
- [CNIL — guia de pseudonimização](https://www.cnil.fr/fr/lanonymisation-des-donnees-un-traitement-cle-pour-lopen-data)

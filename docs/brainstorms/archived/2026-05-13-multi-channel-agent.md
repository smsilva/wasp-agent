# Agente Agno multi-canal — contexto para Claude Code

## Objetivo

Construir um chatbot baseado no **Agno Framework** que possa ser consumido por
múltiplos canais (Telegram, Discord, Slack, e futuramente Google Chat), mantendo
o **core do agente** (modelo LLM, tools, memória, conhecimento)
independente do canal de entrada.

O caso inicial vai apenas criar o agente que responde a mensagens, sem tools, para validar o ciclo de desenvolvimento. Depois, vamos iterar adicionando tools específicas do domínio (MCP server das fitness functions, leitura do EKS/AWS, ArgoCD, DynamoDB, Cognito, OpenTelemetry via MCP server e operações assistidas de plataforma)

Após o caso inicial ser implementado, decidiremos os próximos passos.

## Decisão arquitetural

Padrão **ports-and-adapters / hexagonal**, que é exatamente como o Agno já
estrutura via `AgentOS(interfaces=[...])`:

- **Core** — `Agent` (ou `Team`) do Agno com modelo, tools, instructions,
  storage. Não conhece canais.
- **Adapters** — `agno.os.interfaces.telegram.Telegram`,
  `.discord.Discord`, `.slack.Slack`, etc. Traduzem eventos do canal ↔
  chamadas no agente.
- **AgentOS** — FastAPI que orquestra tudo, expõe REST + AG-UI para debug
  local em `http://localhost:7777`.

```
Canais (TG/Discord/Slack/GChat) → AgentOS (FastAPI) → Agent core → {LLM, Storage, Tools/MCP}
```

## Por que não Google Chat agora

Google Chat App interativo exige Workspace **Business/Enterprise** + projeto
GCP + endpoint HTTPS público (ou Pub/Sub). Sem essa conta no momento.
Webhook só de saída (notificações) funciona em qualquer plano, mas não é
chatbot bidirecional.

Decisão: começar por canais que rodam com conta pessoal grátis. Quando o
acesso enterprise destravar, basta escrever **mais um adaptador** e adicionar
em `interfaces=[]`. Zero mudança no core.

## Canais escolhidos

Ordem de implementação:

1. **Telegram (primeiro)** — `@BotFather` → token → long polling, sem
   endpoint público necessário. Ciclo de feedback de ~5 min.
2. **Discord (segundo)** — Developer Portal → bot token → WebSocket gateway,
   também sem endpoint público. Valida que a abstração de adapters
   funciona com >1 canal.
3. **Slack (opcional)** — workspace grátis funciona com Socket Mode.
4. **AG-UI** — vem de graça com AgentOS, ótimo para debug paralelo.
5. **Google Chat (futuro)** — quando houver conta Workspace
   Business/Enterprise.

## Esqueleto de código de referência

```python
from agno.os import AgentOS
from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.db.postgres import PostgresDb
from agno.os.interfaces.telegram import Telegram
from agno.os.interfaces.discord import Discord
from agno.os.interfaces.slack import Slack
import os

# CORE — independente de canal
db = PostgresDb(db_url=os.getenv("DATABASE_URL"))

infra_agent = Agent(
    name="InfraAgent",
    model=Claude(id="claude-sonnet-4-5"),
    db=db,
    add_history_to_messages=True,
    instructions=[
        "You are an SRE assistant for the aws-saas-platform.",
        "Always confirm destructive actions before executing.",
    ],
    tools=[
        # waspctl, kubectl (read-only), AWS, DynamoDB, MCP fitness functions...
    ],
)

# ADAPTERS — plugáveis condicionalmente via env vars
interfaces = []

if os.getenv("TELEGRAM_TOKEN"):
    interfaces.append(Telegram(agent=infra_agent, token=os.getenv("TELEGRAM_TOKEN")))

if os.getenv("DISCORD_TOKEN"):
    interfaces.append(Discord(agent=infra_agent, token=os.getenv("DISCORD_TOKEN")))

if os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_SIGNING_SECRET"):
    interfaces.append(Slack(
        agent=infra_agent,
        token=os.getenv("SLACK_BOT_TOKEN"),
        signing_secret=os.getenv("SLACK_SIGNING_SECRET"),
        streaming=True,
    ))

agent_os = AgentOS(
    description="aws-saas-platform agent",
    agents=[infra_agent],
    interfaces=interfaces,
    db=db,
    tracing=True,
)

app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(app="main:app", reload=True)
```

Propriedade-chave: **o mesmo binário** suporta zero, um, dois ou todos os
canais dependendo de quais env vars estão setadas. Local você habilita só
Telegram; no EKS, External Secrets injeta o que for relevante por ambiente.

## Regras de portabilidade entre canais

- **`session_id` derivado do canal**, ex: `f"tg:{chat_id}"`,
  `f"dc:{channel_id}:{user_id}"`. Conversas isoladas, storage único.
- **`user_id` separado de `session_id`.** Mesmo humano em Telegram e Discord
  vira `user_id`s diferentes a menos que se implemente identidade
  unificada (deixar pra depois).
- **Tools são canal-agnósticas.** Nenhuma tool deve saber em qual canal
  está rodando. Mensagens proativas (alertas etc.) são responsabilidade
  de workflows agendados, não de tools.
- **Centralized persistence.** Único Postgres (Docker local → RDS em
  produção). Memória, sessões e traces todos lá.

## Considerações de infra (alinhado com o stack atual)

- **Deploy:** AgentOS é FastAPI → Dockerfile → ECR → manifest K8s →
  ArgoCD sincroniza. Encaixa direto no GitOps existente.
- **Secrets:** tokens de bot, DB URL, API keys de LLM → External Secrets
  Operator puxando do AWS Secrets Manager.
- **Observabilidade:** AgentOS tem hooks de tracing OTel — apontar
  exporter pro Tempo da stack Grafana já planejada (Tempo/Mimir/Loki).
- **MCP:** fitness functions OTel expostas como MCP server podem virar
  tools do agente. Usuário pergunta "como está a aderência do tenant X
  ao Well-Architected?" → agente chama MCP.
- **Local models:** dá pra apontar pro LM Studio na m15 (RTX 3070)
  durante desenvolvimento, custo zero de tokens.

## Roadmap

1. Telegram + Claude + SQLite local. Agente único, sem tools. Valida ciclo.
2. Adicionar Discord no mesmo binário. Confirma abstração de adaptadores.
3. Plugar MCP server das fitness functions + tools de leitura do EKS/AWS.
4. Refatorar core para `Team` (InfraAgent, SecurityAgent, NetworkAgent,
   DocsAgent). Adaptadores apontam pro Team.
5. Deploy no EKS via ArgoCD. External Secrets para tokens.
6. Adapter Google Chat quando Workspace Enterprise estiver disponível.

## Próximos passos sugeridos

- **Opção A:** quickstart executável Telegram + Agno + Docker Compose
  (Postgres) rodando localmente.
- **Opção B:** ir direto pra modelagem das tools que expõem as fitness
  functions via MCP.

## Referências

- Docs Agno: <https://docs.agno.com/>
- Repo Agno: <https://github.com/agno-agi/agno>
- Template de referência (Slack pré-conectado, padrão de adaptadores):
  <https://github.com/agno-agi/agent-platform-railway>
- Agno docs como MCP server para coding agents:
  `docs.agno.com/mcp`

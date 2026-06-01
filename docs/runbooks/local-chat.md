# Local chat — interagir com o agent via curl

Caminho de validação manual sem Telegram ([`validation-local-chat.md`](validation-local-chat.md)). Útil para iterar sobre `INSTRUCTIONS`, memória de sessão e ciclo de provisionamento.

## Pré-requisitos

- `curl`, `jq`, `uuidgen` no PATH.
- Para o happy path completo (provision + notificação async): cluster com ArgoCD + Crossplane + Composition, `GH_PAT` válido. Ver [`validation-gitops.md`](validation-gitops.md).

Para validação só do LLM (sem provisionar), basta o agent rodando — recuse a confirmação no passo de criação.

## Setup

Sem Telegram:

```bash
unset TELEGRAM_TOKEN
make run
```

O log do servidor inicia com o `ConsoleNotifier` selecionado (default sem `TELEGRAM_TOKEN`). Para forçar, exporte `AGENT_NOTIFIER=console`.

## Uso manual

Em outro terminal:

```bash
scripts/local-chat --new-session
scripts/local-chat "oi"
scripts/local-chat "Meu nome é João."
scripts/local-chat "Qual é o meu nome?"
scripts/local-chat "Crie uma plataforma chamada wp-demo na região us-east-1."
scripts/local-chat "Sim, confirma."
```

Quando o `Platform` ficar `Ready=True`, o `ConsoleNotifier` escreve no log do `make run`:

```
[AGENT_NOTIFIER chat_id=abc12345] Plataforma 'wp-demo' está pronta.
- us-east-1: https://gateway.us-east-1.wp-demo.wasp.silvios.me
```

## Roteiro scripted

```bash
make local-chat
```

Roda os 5 turnos automaticamente. Sem cluster configurado, o passo 5 retorna erro do tool — esperado.

## Estado da sessão

`session_id` persiste em `.wasp-cli/session` (cwd-local, ignorado pelo git). Para zerar:

```bash
scripts/local-chat --new-session
```

## Variáveis

| Var | Default | Observação |
|---|---|---|
| `AGENT_NOTIFIER` | auto (`telegram` se `TELEGRAM_TOKEN`, senão `console`) | Força a escolha |
| `AGENT_URL` | `http://localhost:7777` | URL base do servidor |
| `AGENT_ID` | `wasp-agent` | ID do agent no AgentOS |

# Exploração: Padrão `wasp/clients/` para o restante do código

**Date:** 2026-05-26  
**Status:** Idea

## Problema

A refatoração inicial (`docs/sdlc/02-design/archived/2026-05-26-clients-package-design.md`) move o código do Telegram e o `ConsoleNotifier` para `wasp/clients/`. O restante de `wasp/` ainda mistura responsabilidades sem um padrão claro de agrupamento por domínio.

## Pergunta a responder

Quais outros módulos de `wasp/` são específicos de um "cliente" ou canal e deveriam seguir o mesmo padrão?

## Candidatos óbvios

| Módulo atual | Possível destino | Motivo |
|---|---|---|
| `wasp/git_client.py` | `wasp/clients/git/` ou manter | Acessa Gitea via HTTP — é um cliente de serviço externo |
| `wasp/gitops_committer.py` | `wasp/clients/git/` ou `wasp/gitops/` | Depende de `git_client`, opera sobre repositórios |
| `wasp/platform_cluster.py` | `wasp/clients/k8s/` ou `wasp/k8s/` | Lê estado de clusters Kubernetes |

## Questões em aberto

- O padrão `clients/` faz sentido apenas para canais de notificação, ou também para clientes de infraestrutura (Git, k8s)?
- Alternativa: usar `wasp/integrations/` para serviços externos e manter `wasp/clients/` só para canais de notificação?
- Vale agrupar `git_client` + `gitops_committer` juntos ou mantê-los separados?

## Próximos passos sugeridos

Quando chegar a hora de adicionar Discord/Slack ou mexer em `git_client`/`platform_cluster`, abrir um brainstorming para decidir se o padrão se expande e como.

# Design: Apêndice expandido — fluxo GitOps completo via Telegram

**Date:** 2026-05-23  
**Status:** Approved  
**Scope:** Expandir o Apêndice de `validation.md` com passos detalhados para executar o ciclo completo: Telegram → commit em `wasp-gitops` → ArgoCD sync → Crossplane reconcile → notificação Ready no Telegram.

---

## Contexto

O Apêndice atual em `validation.md` tem apenas 3 bullets sem detalhes. A execução manual mostrou que faltam: auth bootstrap, verificação do cluster, e critérios de sucesso em cada etapa. O resultado foi o erro `Acesso negado` por tabela de auth vazia.

## Objetivo

Tornar o Apêndice auto-suficiente: quem o seguir do zero chega à notificação Ready no Telegram sem consultar outros runbooks (exceto para setup inicial de ngrok e GitHub PAT, que permanecem em seus arquivos dedicados).

## Pré-requisitos adicionais (além do smoke test básico B.1)

- `k3d`, `helm`, `kubectl` instalados
- `~/git/kubernetes` clonado (`git clone https://github.com/smsilva/kubernetes ~/git/kubernetes`)
- `GH_PAT` no `.env` com `Contents: write` em `smsilva/wasp-gitops`
- ngrok rodando + webhook registrado (pré-requisito do smoke test B)

## Sequência de comandos

```
1. make gitops-up
2. make admin-bootstrap NAME="<nome>" CHANNEL=tg ID=<chat_id>
3. make run
4. [Telegram] solicitar criação de plataforma, confirmar
5. aguardar Ready (~5–15 min: ArgoCD sync + Crossplane reconcile)
6. make gitops-down
```

## Critérios de verificação por etapa

| Etapa | Verificação |
|---|---|
| `make gitops-up` | `kubectl get pods -A` todos Running; `argocd app get wasp-gitops` Synced/Healthy |
| `make admin-bootstrap` | `make admin-list` exibe usuário com canal `tg` e `chat_id` corretos |
| `make run` | Agente sobe sem erro; `getWebhookInfo` sem `last_error_message` |
| Confirmação no Telegram | Bot confirma início do provisionamento; commit visível em `smsilva/wasp-gitops` |
| Notificação Ready | Mensagem Ready chega no Telegram; `kubectl get platform` mostra `Ready=True` |

## O que muda em `validation.md`

- Apêndice existente: substituir os 3 bullets por uma seção estruturada com pré-requisitos, sequência, critérios de verificação e nota sobre tempo de ciclo.
- Nenhum outro arquivo é alterado.

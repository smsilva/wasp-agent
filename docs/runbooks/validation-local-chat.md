# Local chat — manual, sem Telegram

Equivalente ao smoke test Telegram, mas usando `curl` / `scripts/local-chat`. Ver [`local-chat.md`](local-chat.md).

Útil para iteração rápida em system prompt, memória de sessão e fluxo de confirmação sem montar ngrok + bot.

```bash
unset TELEGRAM_TOKEN
make run

# em outro terminal
make local-chat
```

Para o happy-path com notificação `Ready` (passos 4-5 do roteiro chegam a `provision_platform_instance` rodando de verdade), o setup de infra é o de [`validation-gitops.md`](validation-gitops.md).

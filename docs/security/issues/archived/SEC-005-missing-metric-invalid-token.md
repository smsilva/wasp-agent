---
id: SEC-005
severity: Low
status: resolved
opened: 2026-05-25
resolved: 2026-05-25
---

# SEC-005: Metric `wasp_auth_denied_total` não emitida em token de invite inválido

## Descrição

Em `main.py::_process_start_token`, quando `redeem_invite` retorna `None` (token
inválido, expirado ou já usado), nenhuma métrica era emitida. Ataques de replay
ou tentativas de scan de tokens eram invisíveis em Prometheus.

## Impacto

Incidentes de abuso de invite (replay, token expirado enviado por terceiro) não
aparecem em alertas ou dashboards. A entropia de 256 bits torna brute-force
inviável, mas replay de tokens interceptados (e.g. compartilhados em grupo)
ficaria invisível.

## Fix

Adicionado `telemetry.auth_denied(channel="tg", reason="invalid_token")` no branch
`result is None` de `_process_start_token`.

Coberto pela asserção `denied == [{"channel": "tg", "reason": "invalid_token"}]`
adicionada a `tests/test_main.py::test_start_token_invalid_sends_error_message`.

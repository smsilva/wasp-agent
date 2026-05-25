---
id: SEC-004
severity: High
status: resolved
opened: 2026-05-25
resolved: 2026-05-25
---

# SEC-004: TOCTOU race em `redeem_invite` — double-claim de invite sem binding

## Descrição

`redeem_invite` em `wasp/auth.py` lia `used_at` via `SELECT` fora de qualquer
transação de escrita (DEFERRED, sem RESERVED lock). Dois requests simultâneos com
o mesmo token sem binding (`channel=None`) podiam ambos ver `used_at=NULL`, passar
todas as verificações em Python, e ambos committar com `channel_id` distintos — sem
conflito de PK em `auth_identities`.

## Impacto

Um invite single-use poderia vincular **dois** usuários distintos ao mesmo `user_id`,
permitindo acesso não autorizado a quem recebesse (ou interceptasse) o link de convite.

## Fix

Adicionado `con.execute("BEGIN IMMEDIATE")` antes do `SELECT` em `redeem_invite`.
O RESERVED lock é adquirido imediatamente; o segundo thread espera o COMMIT do
primeiro e então vê `used_at` definido, retornando `None`.

Coberto por `tests/test_auth.py::test_redeem_invite_concurrent_unbound_token_only_succeeds_once`
(threading test com `threading.Barrier`).
